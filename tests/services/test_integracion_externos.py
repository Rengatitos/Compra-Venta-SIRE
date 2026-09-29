"""Paso de los comprobantes de Apaclla Bot a su periodo.

Corre sobre una base en memoria con la API de Motor que usan los repositorios,
así que también cubre las consultas de `comprobantes`, `comprobantes_externos`
y `periodos`, no sólo el servicio.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from bson import ObjectId
from bson.decimal128 import Decimal128

from app.domain.comprobante import Libro, Origen
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import comprobantes_externos as repo_externos
from app.repositories import periodos as repo_periodos
from app.repositories._mongo import (
    NOMBRE_COL_COMPROBANTES,
    NOMBRE_COL_COMPROBANTES_EXTERNOS,
    NOMBRE_COL_PERIODOS,
)
from app.services import comprobantes_externos_service, integracion_externos

EMPRESA_ID = "65f000000000000000000001"
PERIODO = "202609"

# --- Base en memoria -----------------------------------------------------------


def _casa_valor(valor: Any, condicion: Any, presente: bool) -> bool:
    if isinstance(condicion, dict) and any(k.startswith("$") for k in condicion):
        for operador, argumento in condicion.items():
            if operador == "$in" and valor not in argumento:
                return False
            if operador == "$ne" and valor == argumento:
                return False
            if operador == "$exists" and presente != argumento:
                return False
            if operador == "$gt" and not (valor is not None and valor > argumento):
                return False
        return True
    return valor == condicion


def _casa(documento: dict, filtro: dict) -> bool:
    for clave, condicion in filtro.items():
        if clave == "$or":
            if not any(_casa(documento, f) for f in condicion):
                return False
        elif clave == "$nor":
            if any(_casa(documento, f) for f in condicion):
                return False
        elif not _casa_valor(documento.get(clave), condicion, clave in documento):
            return False
    return True


class Cursor:
    def __init__(self, filas: list[dict]):
        self._filas = filas

    def sort(self, campo, direccion=1):
        self._filas.sort(key=lambda d: d.get(campo), reverse=direccion == -1)
        return self

    def skip(self, n):
        self._filas = self._filas[n:]
        return self

    def limit(self, n):
        self._filas = self._filas[:n] if n else self._filas
        return self

    async def to_list(self, length=None):
        return copy.deepcopy(self._filas[:length] if length else self._filas)


class Resultado:
    def __init__(self, modificados=0, borrados=0):
        self.modified_count = modificados
        self.deleted_count = borrados
        self.upserted_id = None


class Coleccion:
    def __init__(self):
        self.docs: list[dict] = []

    def find(self, filtro=None, _proyeccion=None):
        return Cursor([d for d in self.docs if _casa(d, filtro or {})])

    async def find_one(self, filtro, _proyeccion=None):
        filas = await self.find(filtro).to_list()
        return filas[0] if filas else None

    async def insert_one(self, documento):
        documento.setdefault("_id", ObjectId())
        self.docs.append(copy.deepcopy(documento))

    async def update_one(self, filtro, cambio, upsert=False):
        for documento in self.docs:
            if _casa(documento, filtro):
                documento.update(copy.deepcopy(cambio.get("$set", {})))
                return Resultado(modificados=1)
        if upsert:
            nuevo = {k: v for k, v in filtro.items() if not k.startswith("$")}
            nuevo.update(copy.deepcopy(cambio.get("$setOnInsert", {})))
            nuevo.update(copy.deepcopy(cambio.get("$set", {})))
            await self.insert_one(nuevo)
        return Resultado()

    async def update_many(self, filtro, cambio):
        filas = [d for d in self.docs if _casa(d, filtro)]
        for documento in filas:
            documento.update(copy.deepcopy(cambio["$set"]))
        return Resultado(modificados=len(filas))

    async def delete_one(self, filtro):
        for documento in self.docs:
            if _casa(documento, filtro):
                self.docs.remove(documento)
                return Resultado(borrados=1)
        return Resultado()

    async def count_documents(self, filtro):
        return sum(1 for d in self.docs if _casa(d, filtro))

    async def distinct(self, campo, filtro):
        return list({d.get(campo) for d in self.docs if _casa(d, filtro)})


class Base(dict):
    def __missing__(self, nombre):
        self[nombre] = Coleccion()
        return self[nombre]

    @property
    def externos(self) -> Coleccion:
        return self[NOMBRE_COL_COMPROBANTES_EXTERNOS]

    @property
    def comprobantes(self) -> Coleccion:
        return self[NOMBRE_COL_COMPROBANTES]


def correr(corutina):
    return asyncio.run(corutina)


@pytest.fixture
def db() -> Base:
    return Base()


# --- Datos -----------------------------------------------------------------------


def _externo(**cambios) -> dict:
    documento = {
        "_id": ObjectId(),
        "empresa_id": EMPRESA_ID,
        "id_externo": str(ObjectId()),
        "libro": "compras",
        "fuente": "factura",
        "tipo_evidencia": "comprobante",
        "tipo_cp": "01",
        "serie": "F001",
        "numero": "00000123",
        "nro_operacion": None,
        "fecha_operacion": datetime(2026, 9, 28, tzinfo=UTC),
        "moneda": "PEN",
        "total": Decimal128("118.00"),
        "base_imponible": Decimal128("100.00"),
        "igv": Decimal128("18.00"),
        "contraparte": {
            "tipo_doc_identidad": "6", "documento": "20100070970", "nombre": "Proveedor"
        },
        "descripcion": "Útiles de oficina",
        "confianza": 0.9,
        "campos_dudosos": [],
        "imagen": {"archivo": None},
        "periodo": PERIODO,
        "estado": "recibido",
        "creado_en": datetime.now(UTC),
        "comprobante_id": None,
    }
    documento.update(cambios)
    return documento


def _yape(**cambios) -> dict:
    return _externo(**{
        "libro": "ventas", "fuente": "yape", "tipo_evidencia": "voucher", "tipo_cp": "00",
        "serie": "", "numero": "", "nro_operacion": "0012345678",
        "total": Decimal128("150.00"), "base_imponible": None, "igv": None,
        "descripcion": "Pago recibido por Yape", **cambios,
    })


def _guardar_externo(db: Base, documento: dict) -> dict:
    correr(db.externos.insert_one(documento))
    return documento


def _crear_periodo(db: Base, periodo: str = PERIODO) -> None:
    correr(db[NOMBRE_COL_PERIODOS].insert_one({"empresa_id": EMPRESA_ID, "periodo": periodo}))


def _fila_sire(db: Base, **cambios) -> dict:
    fila = {
        "_id": ObjectId(), "empresa_id": EMPRESA_ID, "periodo": PERIODO, "libro": "compras",
        "origen": "sire", "tipo_cp": "01", "serie": "F001", "numero": "123",
        "serie_numero": "F001-123",
    }
    fila.update(cambios)
    correr(db.comprobantes.insert_one(fila))
    return fila


def _externo_guardado(db: Base, documento: dict) -> dict:
    return next(d for d in db.externos.docs if d["_id"] == documento["_id"])


# --- Mapeo -----------------------------------------------------------------------


def test_la_factura_entra_con_el_numero_normalizado_como_sunat():
    comprobante = integracion_externos.a_comprobante(_externo())

    assert comprobante.origen is Origen.EXTERNO
    # Los ceros de relleno del número se van, como en la propuesta SUNAT.
    assert (comprobante.tipo_cp, comprobante.serie, comprobante.numero) == ("01", "F001", "123")
    assert comprobante.fecha_emision.isoformat() == "2026-09-28"
    assert comprobante.documento_contraparte == "20100070970"
    assert comprobante.razon_social == "PROVEEDOR"
    assert (comprobante.base_imponible, comprobante.igv) == (Decimal("100.00"), Decimal("18.00"))
    # El Registro de Compras sale por destino: con IGV se asume gravado.
    assert (comprobante.base_imponible_dg, comprobante.igv_dg) == (
        Decimal("100.00"), Decimal("18.00")
    )
    assert comprobante.total == Decimal("118.00")


# --- Integración -----------------------------------------------------------------


def test_sin_periodo_se_queda_en_externos(db):
    externo = _guardar_externo(db, _externo())

    estado = correr(integracion_externos.integrar_uno(db, EMPRESA_ID, externo))

    assert estado == "recibido"
    assert db.comprobantes.docs == []
    assert _externo_guardado(db, externo)["estado"] == "recibido"


def test_al_existir_el_periodo_entra_como_fila_externa(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)

    conteo = correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert conteo == {"integrados": 1, "ya_existian": 0}
    [fila] = db.comprobantes.docs
    assert fila["origen"] == "externo"
    assert fila["serie_numero"] == "F001-123"
    assert fila["glosa"] == "Útiles de oficina"
    assert fila["estado_procesamiento"] == "sire_recibido"
    guardado = _externo_guardado(db, externo)
    assert guardado["estado"] == "integrado"
    assert guardado["comprobante_id"] == str(fila["_id"])
    assert guardado["integrado_en"] is not None


def test_si_el_periodo_ya_lo_tenia_no_hace_nada(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)
    sire = _fila_sire(db)

    conteo = correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID, PERIODO))

    assert conteo == {"integrados": 0, "ya_existian": 1}
    assert db.comprobantes.docs == [sire]
    guardado = _externo_guardado(db, externo)
    assert guardado["estado"] == "ya_existia"
    assert guardado["comprobante_id"] == str(sire["_id"])


def test_el_mismo_numero_en_el_otro_libro_no_cuenta_como_existente(db):
    _guardar_externo(db, _externo())
    _crear_periodo(db)
    _fila_sire(db, libro="ventas")

    conteo = correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert conteo["integrados"] == 1


def test_el_voucher_no_pasa_al_periodo(db):
    yape = _guardar_externo(db, _yape())
    _crear_periodo(db)

    estado = correr(integracion_externos.integrar_uno(db, EMPRESA_ID, yape))
    conteo = correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert estado == "recibido"
    assert conteo == {"integrados": 0, "ya_existian": 0}
    assert db.comprobantes.docs == []
    assert _externo_guardado(db, yape)["estado"] == "recibido"


def test_integrar_dos_veces_deja_una_sola_fila(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    # Otro refresco que leyó el externo antes de que se marcara.
    correr(integracion_externos._integrar(db, EMPRESA_ID, externo))

    assert len(db.comprobantes.docs) == 1


def test_solo_integra_los_de_periodos_que_existen(db):
    septiembre = _guardar_externo(db, _externo())
    octubre = _guardar_externo(
        db,
        _externo(numero="124", periodo="202610", fecha_operacion=datetime(2026, 10, 2, tzinfo=UTC)),
    )
    _crear_periodo(db)

    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    assert _externo_guardado(db, septiembre)["estado"] == "integrado"
    assert _externo_guardado(db, octubre)["estado"] == "recibido"


def test_el_listado_de_externos_integra_los_pendientes(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)

    lista = correr(
        comprobantes_externos_service.listar(
            db, {"_id": EMPRESA_ID, "ruc": "20603391692"},
            libro=None, periodo=None, fuente=None, skip=0, limit=100,
        )
    )

    [item] = lista["items"]
    assert item["id"] == str(externo["_id"])
    assert item["estado"] == "integrado"
    assert item["serie_numero_periodo"] == "F001-123"
    assert item["comprobante_id"] == str(db.comprobantes.docs[0]["_id"])


# --- Propuesta SUNAT ---------------------------------------------------------------


def test_la_propuesta_sunat_reemplaza_a_la_fila_externa(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    fila_externa = db.comprobantes.docs[0]
    fila_externa["clasificacion_contable"] = {"cuenta_base": {"codigo": "6011"}}
    sire = _fila_sire(db)

    reemplazados = correr(
        integracion_externos.reconciliar_con_sunat(db, EMPRESA_ID, PERIODO, Libro.COMPRAS)
    )

    assert reemplazados == 1
    [queda] = db.comprobantes.docs
    assert queda["_id"] == sire["_id"]
    # Lo trabajado sobre la fila externa pasa a la de SUNAT...
    assert queda["clasificacion_contable"] == {"cuenta_base": {"codigo": "6011"}}
    # ...pero no la glosa que sólo era la descripción del bot: manda el detalle SUNAT.
    assert "glosa" not in queda
    guardado = _externo_guardado(db, externo)
    assert guardado["estado"] == "ya_existia"
    assert guardado["comprobante_id"] == str(sire["_id"])


def test_la_glosa_editada_pasa_a_la_fila_sunat(db):
    _guardar_externo(db, _externo())
    _crear_periodo(db)
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    db.comprobantes.docs[0]["glosa"] = "Compra de papel bond"
    _fila_sire(db)

    correr(integracion_externos.reconciliar_con_sunat(db, EMPRESA_ID, PERIODO, Libro.COMPRAS))

    assert db.comprobantes.docs[0]["glosa"] == "Compra de papel bond"


def test_sin_gemela_sunat_la_fila_externa_se_queda(db):
    _guardar_externo(db, _externo())
    _crear_periodo(db)
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))
    _fila_sire(db, numero="999", serie_numero="F001-999")

    reemplazados = correr(
        integracion_externos.reconciliar_con_sunat(db, EMPRESA_ID, PERIODO, Libro.COMPRAS)
    )

    assert reemplazados == 0
    assert {f["origen"] for f in db.comprobantes.docs} == {"externo", "sire"}


# --- Borrar el periodo -------------------------------------------------------------------


def test_al_borrar_el_periodo_el_externo_vuelve_a_esperar(db):
    externo = _guardar_externo(db, _externo())
    _crear_periodo(db)
    correr(integracion_externos.integrar_pendientes(db, EMPRESA_ID))

    correr(repo_externos.devolver_a_pendiente(db, EMPRESA_ID, PERIODO))

    guardado = _externo_guardado(db, externo)
    assert guardado["estado"] == "recibido"
    assert guardado["comprobante_id"] is None


def test_periodos_existentes(db):
    _crear_periodo(db)
    assert correr(repo_periodos.existentes(db, EMPRESA_ID, [PERIODO, "202610"])) == {PERIODO}
    assert correr(repo_periodos.existentes(db, EMPRESA_ID, [])) == set()


def test_desde_documento_acepta_el_origen_externo():
    comprobante = repo_comprobantes.desde_documento({"origen": "externo", "libro": "ventas"})
    assert comprobante.origen is Origen.EXTERNO


def test_el_cuadre_con_sunat_no_cuenta_las_filas_externas():
    from app.api.v1.routes.comprobantes import _solo_sunat

    datos = [{"origen": "sire"}, {"origen": "externo"}, {"origen": "sire"}]
    assert _solo_sunat(datos) == [{"origen": "sire"}, {"origen": "sire"}]


def test_si_la_integracion_falla_el_listado_sigue(db, monkeypatch):
    async def falla(*_args, **_kwargs):
        raise RuntimeError("mongo caído")

    monkeypatch.setattr(integracion_externos, "integrar_pendientes", falla)

    assert correr(integracion_externos.refrescar(db, EMPRESA_ID)) is None
