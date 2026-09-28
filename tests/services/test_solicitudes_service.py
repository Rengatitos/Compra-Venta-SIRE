"""Orquestación de solicitudes: items, encadenado de pasos, ZIP y correo."""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import solicitudes as ruta
from app.core.auth import crear_token_descarga, usuario_actual
from app.db.database import get_db
from app.domain.jobs import EstadoJob, Job, TipoJob
from app.services import solicitudes_service as servicio

RUC_A = "20610202251"
RUC_B = "20603391692"
CORREO = "contador@example.com"


class Memoria:
    """Mongo en memoria para empresas, periodos y solicitudes, y una cola falsa."""

    def __init__(self) -> None:
        self.empresas = {
            RUC_A: {"_id": ObjectId(), "ruc": RUC_A, "nombre": "Alfa",
                    "sunat_client_id": "id", "sunat_client_secret": "s"},
            RUC_B: {"_id": ObjectId(), "ruc": RUC_B, "nombre": "Beta"},
        }
        self.periodos: dict[str, list[str]] = {
            str(self.empresas[RUC_A]["_id"]): ["202607", "202608"],
            str(self.empresas[RUC_B]["_id"]): ["202608"],
        }
        self.solicitudes: dict[str, dict] = {}
        self.encolados: list[Job] = []

    # empresas
    async def listar_empresas(self, db, limit=100):
        return list(self.empresas.values())

    async def empresa_por_ruc(self, db, ruc):
        return self.empresas.get(ruc)

    # periodos
    async def listar_periodos(self, db, empresa_id, limit=100):
        return [{"periodo": p} for p in self.periodos.get(empresa_id, [])]

    async def obtener_periodo(self, db, empresa_id, periodo):
        return {"periodo": periodo} if periodo in self.periodos.get(empresa_id, []) else None

    async def crear_periodo(self, db, empresa_id, periodo, estado="pendiente"):
        self.periodos.setdefault(empresa_id, []).append(periodo)

    # solicitudes
    async def crear(self, db, documento):
        sid = str(ObjectId())
        self.solicitudes[sid] = {**copy.deepcopy(documento), "_id": ObjectId(sid)}
        return sid

    async def obtener(self, db, sid):
        documento = self.solicitudes.get(sid)
        return copy.deepcopy(documento) if documento else None

    async def actualizar(self, db, sid, cambios):
        documento = self.solicitudes[sid]
        for clave, valor in cambios.items():
            partes = clave.split(".")
            destino = documento
            for parte in partes[:-1]:
                destino = destino[int(parte)] if parte.isdigit() else destino[parte]
            ultima = partes[-1]
            if ultima.isdigit():
                destino[int(ultima)] = copy.deepcopy(valor)
            else:
                destino[ultima] = copy.deepcopy(valor)

    async def guardar_item(self, db, sid, indice, item):
        await self.actualizar(db, sid, {f"items.{indice}": item})

    async def reservar_empaquetado(self, db, sid):
        if self.solicitudes[sid]["estado"] != "en_progreso":
            return False
        self.solicitudes[sid]["estado"] = "empaquetando"
        return True

    # cola
    async def encolar(self, db, tipo, ruc, periodo, libro=None, **kwargs):
        job = Job(tipo=tipo, ruc=ruc, periodo=periodo, libro=libro, gestionado=True, **kwargs)
        self.encolados.append(job)
        return job


@pytest.fixture
def mem(monkeypatch):
    m = Memoria()
    monkeypatch.setattr(servicio.repo_empresas, "listar", m.listar_empresas)
    monkeypatch.setattr(servicio.repo_empresas, "obtener_por_ruc", m.empresa_por_ruc)
    monkeypatch.setattr(servicio.repo_periodos, "listar", m.listar_periodos)
    monkeypatch.setattr(servicio.repo_periodos, "obtener", m.obtener_periodo)
    monkeypatch.setattr(servicio.repo_periodos, "crear", m.crear_periodo)
    for nombre in ("crear", "obtener", "actualizar", "guardar_item", "reservar_empaquetado"):
        monkeypatch.setattr(servicio.repo_solicitudes, nombre, getattr(m, nombre))
    monkeypatch.setattr(servicio.cola, "encolar", m.encolar)
    monkeypatch.setattr(servicio.repo_jobs, "listar_de_solicitud", AsyncMock(return_value=[]))
    monkeypatch.setattr(servicio.settings, "CLASIFICADOR_HABILITADO", True)
    servicio.jobs_service._candados.clear()
    return m


def crear(**kwargs):
    base = {"creado_por": CORREO, "empresas": "todas", "periodos": "todos"}
    return asyncio.run(servicio.crear(None, **{**base, **kwargs}))


def cerrar(mem, job, estado=EstadoJob.COMPLETADO, resultado=None, error=None):
    job.estado = estado
    job.resultado = resultado or {}
    job.error = error
    asyncio.run(servicio.al_terminar(None, job))


def test_todas_las_empresas_por_todos_sus_periodos(mem):
    solicitud = crear()

    assert [(i["ruc"], i["periodo"]) for i in solicitud["items"]] == [
        (RUC_A, "202607"), (RUC_A, "202608"), (RUC_B, "202608"),
    ]
    # El primer paso de cada item queda encolado. Beta no tiene credenciales.
    primeros = [(j.ruc, j.tipo) for j in mem.encolados]
    assert primeros == [
        (RUC_A, TipoJob.SINCRONIZACION_SIRE),
        (RUC_A, TipoJob.SINCRONIZACION_SIRE),
        (RUC_B, TipoJob.CREDENCIALES_SUNAT),
    ]
    assert all(j.solicitud_id == str(solicitud["_id"]) for j in mem.encolados)
    assert mem.encolados[2].cola == RUC_B  # la sesión SOL de Beta


def test_periodos_concretos_crean_los_que_falten_y_rechazan_el_futuro(mem):
    crear(empresas=[RUC_B], periodos=["202606"])
    assert "202606" in mem.periodos[str(mem.empresas[RUC_B]["_id"])]

    with pytest.raises(servicio.SolicitudInvalida):
        crear(empresas=[RUC_B], periodos=["209912"])
    with pytest.raises(servicio.SolicitudInvalida):
        crear(empresas=["20100070970"], periodos=["202608"])


def test_sin_clasificador_la_clasificacion_se_omite(mem, monkeypatch):
    monkeypatch.setattr(servicio.settings, "CLASIFICADOR_HABILITADO", False)
    solicitud = crear(empresas=[RUC_A], periodos=["202608"])
    omitidos = [p for p in solicitud["items"][0]["pasos"] if p["estado"] == "omitido"]
    assert {p["paso"] for p in omitidos} == {"clasificacion_compras", "clasificacion_ventas"}


def test_cada_paso_completado_encola_el_siguiente_hasta_el_zip_y_el_correo(mem):
    solicitud = crear(empresas=[RUC_A], periodos=["202608"])
    sid = str(solicitud["_id"])

    tipos = []
    while True:
        job = mem.encolados[-1]
        tipos.append((job.tipo, job.libro.value if job.libro else None))
        if job.tipo is TipoJob.ENVIO_CORREO:
            break
        zip_ = {"archivo": "DESCARGA.zip", "bytes": 10}
        cerrar(mem, job, resultado=zip_ if job.tipo is TipoJob.EMPAQUETADO else {})

    assert tipos == [
        (TipoJob.SINCRONIZACION_SIRE, "compras"),
        (TipoJob.SINCRONIZACION_SIRE, "ventas"),
        (TipoJob.EXTRACCION_DETALLES, "compras"),
        (TipoJob.EXTRACCION_DETALLES, "ventas"),
        (TipoJob.CLASIFICACION_CUENTAS, "compras"),
        (TipoJob.CLASIFICACION_CUENTAS, "ventas"),
        (TipoJob.EMPAQUETADO, None),
        (TipoJob.ENVIO_CORREO, None),
    ]
    assert mem.encolados[2].parametros["hasta_terminar"] is True
    assert mem.encolados[4].parametros["automatica"] is True
    assert mem.solicitudes[sid]["items"][0]["estado"] == "completado"
    assert mem.solicitudes[sid]["estado"] == "enviando"
    assert mem.solicitudes[sid]["zip"]["archivo"] == "DESCARGA.zip"

    mem.solicitudes[sid]["envios"] = [{"estado": "enviado"}]
    cerrar(mem, mem.encolados[-1])
    assert mem.solicitudes[sid]["estado"] == "completada"
    assert mem.solicitudes[sid]["terminado_en"] is not None


def test_si_falla_sire_se_omite_el_resto_y_el_item_falla(mem):
    solicitud = crear(empresas=[RUC_A], periodos=["202608"])
    sid = str(solicitud["_id"])

    cerrar(mem, mem.encolados[-1], estado=EstadoJob.FALLIDO, error="SUNAT 401")

    item = mem.solicitudes[sid]["items"][0]
    assert item["estado"] == "fallido"
    assert [p["estado"] for p in item["pasos"][1:]] == ["omitido"] * 5
    assert "SUNAT 401" in item["observaciones"][0]
    # Sin items vivos se empaqueta igual: la carpeta lleva sus observaciones.
    assert mem.encolados[-1].tipo is TipoJob.EMPAQUETADO


def test_un_fallo_despues_de_sire_no_corta_el_item(mem):
    crear(empresas=[RUC_A], periodos=["202608"])
    cerrar(mem, mem.encolados[-1])  # SIRE compras
    cerrar(mem, mem.encolados[-1])  # SIRE ventas
    cerrar(mem, mem.encolados[-1], estado=EstadoJob.FALLIDO, error="portal caído")

    assert mem.encolados[-1].tipo is TipoJob.EXTRACCION_DETALLES
    assert mem.encolados[-1].libro.value == "ventas"


def test_el_empaquetado_se_encola_una_sola_vez(mem):
    solicitud = crear(empresas=[RUC_A, RUC_B], periodos=["202608"], clasificar=False)
    sid = str(solicitud["_id"])
    cerrados: set[str] = set()
    while abiertos := [
        j for j in mem.encolados
        if j.job_id not in cerrados and j.tipo is not TipoJob.EMPAQUETADO
    ]:
        for job in abiertos:
            cerrados.add(job.job_id)
            cerrar(mem, job, estado=EstadoJob.FALLIDO, error="x")

    empaquetados = [j for j in mem.encolados if j.tipo is TipoJob.EMPAQUETADO]
    assert len(empaquetados) == 1
    assert mem.solicitudes[sid]["estado"] == "empaquetando"


def test_un_aviso_repetido_no_duplica_pasos(mem):
    crear(empresas=[RUC_A], periodos=["202608"])
    primero = mem.encolados[-1]
    cerrar(mem, primero)
    cerrar(mem, primero)
    assert len(mem.encolados) == 2


def test_reintentar_reabre_lo_fallido_y_lo_omitido_por_sire(mem):
    solicitud = crear(empresas=[RUC_A], periodos=["202608"])
    sid = str(solicitud["_id"])
    cerrar(mem, mem.encolados[-1], estado=EstadoJob.FALLIDO, error="SUNAT 401")

    asyncio.run(servicio.reintentar(None, sid))

    item = mem.solicitudes[sid]["items"][0]
    assert item["estado"] == "en_progreso"
    assert item["pasos"][0]["estado"] == "encolado"
    assert all(p["estado"] == "pendiente" for p in item["pasos"][1:])
    assert mem.solicitudes[sid]["estado"] == "en_progreso"
    assert mem.encolados[-1].tipo is TipoJob.SINCRONIZACION_SIRE


def test_sin_nada_fallido_no_hay_que_reintentar(mem):
    solicitud = crear(empresas=[RUC_A], periodos=["202608"])
    with pytest.raises(servicio.SolicitudInvalida):
        asyncio.run(servicio.reintentar(None, str(solicitud["_id"])))


# --- Rutas ------------------------------------------------------------------


@pytest.fixture
def cliente(mem):
    ruta.limiter.reset()
    app = FastAPI()
    app.state.limiter = ruta.limiter
    app.include_router(ruta.router, prefix="/solicitudes")
    app.include_router(ruta.router_descargas, prefix="/descargas")
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[usuario_actual] = lambda: {"email": CORREO, "rol": "admin"}
    return TestClient(app)


def test_la_ruta_crea_la_solicitud_con_el_correo_de_la_sesion(cliente, mem):
    r = cliente.post("/solicitudes", json={"empresas": [RUC_A], "periodos": ["202608"]})
    assert r.status_code == 202
    cuerpo = r.json()
    assert cuerpo["creado_por"] == CORREO
    assert cuerpo["progreso"] == {"actual": 0, "total": 1}
    assert cuerpo["items"][0]["pasos"][0]["estado"] == "encolado"


def test_la_ruta_rechaza_una_seleccion_invalida(cliente):
    r = cliente.post("/solicitudes", json={"empresas": [RUC_A], "periodos": ["2026-08"]})
    assert r.status_code == 422


def test_el_enlace_del_correo_descarga_el_zip_y_nada_fuera_de_su_carpeta(
    cliente, monkeypatch, tmp_path
):
    sid = str(ObjectId())
    carpeta = tmp_path / sid
    carpeta.mkdir()
    (carpeta / "DESCARGA_2026-09-27.zip").write_bytes(b"PK")
    (tmp_path / "otro.zip").write_bytes(b"PK")
    monkeypatch.setattr(ruta.empaquetado_service, "raiz_solicitud", lambda s: tmp_path / s)

    ok = cliente.get(f"/descargas/{crear_token_descarga(sid, 'DESCARGA_2026-09-27.zip', 7)}")
    assert ok.status_code == 200
    assert ok.content == b"PK"

    fuera = cliente.get(f"/descargas/{crear_token_descarga(sid, '../otro.zip', 7)}")
    assert fuera.status_code == 404
    assert cliente.get("/descargas/no-es-un-token").status_code == 401


def test_un_token_de_sesion_no_abre_descargas(cliente):
    from app.core.auth import create_token

    assert cliente.get(f"/descargas/{create_token(CORREO)}").status_code == 401


def test_detalle_une_el_estado_vivo_de_cada_paso(mem, monkeypatch):
    solicitud = crear(empresas=[RUC_A], periodos=["202608"])
    job = mem.encolados[-1]
    job.estado = EstadoJob.PENDIENTE
    job.intentos = 2
    job.siguiente_intento_en = datetime(2026, 9, 27, 12, tzinfo=UTC)
    monkeypatch.setattr(servicio.repo_jobs, "listar_de_solicitud", AsyncMock(return_value=[job]))

    detalle = asyncio.run(servicio.detalle(None, mem.solicitudes[str(solicitud["_id"])]))

    paso = detalle["items"][0]["pasos"][0]
    assert paso["intentos"] == 2
    assert paso["siguiente_intento_en"] == job.siguiente_intento_en
