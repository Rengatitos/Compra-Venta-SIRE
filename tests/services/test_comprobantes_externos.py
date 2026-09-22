"""Comprobantes que manda sire-bot: validación, idempotencia, duplicados y foto."""

import base64
import hashlib
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from bson.decimal128 import Decimal128
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.api.v1 import deps
from app.api.v1.routes import comprobantes_externos as ruta
from app.core.auth import usuario_actual
from app.core.config import settings
from app.db.database import get_db
from app.schemas.comprobante_externo import ComprobanteExternoCreate
from app.services import comprobantes_externos_service as servicio

CLAVE = "clave-del-bot-para-pruebas"
RUC = "20603391692"
OTRO_RUC = "20111111111"
EMPRESAS = {
    RUC: {"_id": "65f000000000000000000001", "ruc": RUC, "nombre": "BODEGA"},
    OTRO_RUC: {"_id": "65f000000000000000000002", "ruc": OTRO_RUC, "nombre": "OTRA"},
}
BOT = {"X-Api-Key": CLAVE}
FOTO = b"\xff\xd8\xff\xe0" + b"jpeg-de-prueba" * 20


class ExternosFalsos:
    """Imita `app.repositories.comprobantes_externos`, índices únicos incluidos."""

    def __init__(self):
        self.docs: list[dict] = []

    async def por_id_externo(self, _db, empresa_id, id_externo):
        return next(
            (
                d
                for d in self.docs
                if d["empresa_id"] == empresa_id and d["id_externo"] == id_externo
            ),
            None,
        )

    async def insertar(self, _db, documento):
        for d in self.docs:
            if d["empresa_id"] != documento["empresa_id"]:
                continue
            if d["id_externo"] == documento["id_externo"]:
                raise DuplicateKeyError("uniq_externo_id_externo")
            if (
                documento["nro_operacion"]
                and d["fuente"] == documento["fuente"]
                and d["nro_operacion"] == documento["nro_operacion"]
            ):
                raise DuplicateKeyError("uniq_externo_operacion")
            if documento["tipo_evidencia"] == "comprobante" and all(
                d[k] == documento[k]
                for k in ("tipo_evidencia", "libro", "tipo_cp", "serie", "numero")
            ):
                raise DuplicateKeyError("uniq_externo_serie_numero")
        self.docs.append(documento)

    async def conflicto(self, _db, empresa_id, documento):
        return next(
            (
                d
                for d in self.docs
                if d["empresa_id"] == empresa_id
                and d["fuente"] == documento["fuente"]
                and d["nro_operacion"] == documento["nro_operacion"]
            ),
            None,
        )

    async def listar(self, _db, empresa_id, *, libro, periodo, fuente, skip, limit):
        filas = [
            d
            for d in self.docs
            if d["empresa_id"] == empresa_id
            and (not libro or d["libro"] == libro)
            and (not periodo or d["periodo"] == periodo)
            and (not fuente or d["fuente"] == fuente)
        ]
        return filas[skip : skip + limit], len(filas)

    async def periodos(self, _db, empresa_id, libro=None):
        return sorted(
            {d["periodo"] for d in self.docs if d["empresa_id"] == empresa_id}, reverse=True
        )

    async def obtener(self, _db, empresa_id, id_):
        return next(
            (d for d in self.docs if d["empresa_id"] == empresa_id and str(d["_id"]) == id_), None
        )


@pytest.fixture
def externos(monkeypatch, tmp_path):
    falsos = ExternosFalsos()
    monkeypatch.setattr(servicio, "repo_externos", falsos)
    monkeypatch.setattr(settings, "COMPROBANTES_EXTERNOS_DIR", str(tmp_path))
    return falsos


@pytest.fixture
def cliente(monkeypatch, externos):
    monkeypatch.setattr(settings, "SIRE_BOT_API_KEY", CLAVE)
    monkeypatch.setattr(
        deps.repo_empresas,
        "obtener_por_ruc",
        AsyncMock(side_effect=lambda _db, ruc: EMPRESAS.get(ruc)),
    )
    ruta.limiter.reset()

    app = FastAPI()
    app.state.limiter = ruta.limiter
    app.include_router(ruta.router, prefix="/empresas/{ruc}/comprobantes-externos")
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[usuario_actual] = lambda: {"email": "prueba@example.com"}
    return TestClient(app)


def _yape(**cambios) -> dict:
    cuerpo = {
        "id_externo": "01J8ZYAPE000000000000000001",
        "libro": "ventas",
        "fuente": "yape",
        "tipo_evidencia": "voucher",
        "tipo_cp": "00",
        "serie": "",
        "numero": "",
        "nro_operacion": "12345678",
        "fecha_operacion": "2026-09-19",
        "hora_operacion": "14:32",
        "moneda": "PEN",
        "total": "150.00",
        "base_imponible": None,
        "igv": None,
        "contraparte": {"tipo_doc_identidad": "1", "documento": "45678912", "nombre": "JUAN PEREZ"},
        "descripcion": "Pago recibido por Yape",
        "confianza": 0.93,
        "campos_dudosos": [],
        "imagen": {
            "sha256": hashlib.sha256(FOTO).hexdigest(),
            "mime": "image/jpeg",
            "bytes": len(FOTO),
            "contenido_base64": base64.b64encode(FOTO).decode(),
        },
        "dispositivo_id": "web-123",
        "enviado_en": "2026-09-19T19:32:10Z",
    }
    cuerpo.update(cambios)
    return cuerpo


def _enviar(cliente, cuerpo, ruc=RUC):
    return cliente.post(f"/empresas/{ruc}/comprobantes-externos", json=cuerpo, headers=BOT)


# --- Contrato ----------------------------------------------------------------


def test_voucher_sin_numero_de_operacion_no_pasa():
    with pytest.raises(ValidationError, match="nro_operacion"):
        ComprobanteExternoCreate(**_yape(nro_operacion=""))


def test_voucher_con_tipo_cp_distinto_de_00_no_pasa():
    with pytest.raises(ValidationError, match="tipo_cp"):
        ComprobanteExternoCreate(**_yape(tipo_cp="01"))


def test_comprobante_exige_serie_y_numero():
    with pytest.raises(ValidationError, match="serie y numero"):
        ComprobanteExternoCreate(
            **_yape(tipo_evidencia="comprobante", fuente="factura", tipo_cp="01", serie="F001")
        )


@pytest.mark.parametrize("total", [150.0, "150.5", "1,234.50"])
def test_los_montos_viajan_como_texto_con_dos_decimales(total):
    with pytest.raises(ValidationError, match="total"):
        ComprobanteExternoCreate(**_yape(total=total))


def test_los_montos_se_leen_como_decimal():
    datos = ComprobanteExternoCreate(**_yape(total="1234.50", igv="188.31"))
    assert datos.total == Decimal("1234.50")
    assert datos.igv == Decimal("188.31")


# --- Recepción ---------------------------------------------------------------


def test_recibir_crea_el_comprobante_con_su_periodo(cliente, externos, tmp_path):
    respuesta = _enviar(cliente, _yape())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["ruc"] == RUC
    assert cuerpo["periodo"] == "202609"
    assert cuerpo["estado"] == "recibido"
    assert cuerpo["creado_en"].endswith("Z")

    [documento] = externos.docs
    assert str(documento["_id"]) == cuerpo["id"]
    assert isinstance(documento["total"], Decimal128)
    assert documento["imagen"]["archivo"] == f"{cuerpo['id']}.jpg"
    assert (tmp_path / EMPRESAS[RUC]["_id"] / f"{cuerpo['id']}.jpg").read_bytes() == FOTO


def test_reintentar_el_mismo_id_externo_es_idempotente(cliente, externos):
    primero = _enviar(cliente, _yape())
    segundo = _enviar(cliente, _yape())

    assert primero.status_code == 201
    assert segundo.status_code == 200
    assert segundo.json() == primero.json()
    assert len(externos.docs) == 1


def test_el_mismo_voucher_con_otro_id_externo_es_409(cliente, externos, tmp_path):
    primero = _enviar(cliente, _yape()).json()

    respuesta = _enviar(cliente, _yape(id_externo="01J8ZYAPE000000000000000002"))

    assert respuesta.status_code == 409
    assert respuesta.json()["comprobante_externo_id"] == primero["id"]
    assert len(externos.docs) == 1
    # La foto del rechazado no se queda huérfana en disco.
    assert len(list((tmp_path / EMPRESAS[RUC]["_id"]).iterdir())) == 1


def test_el_mismo_voucher_en_otra_empresa_si_entra(cliente, externos):
    assert _enviar(cliente, _yape()).status_code == 201
    assert _enviar(cliente, _yape(), ruc=OTRO_RUC).status_code == 201
    assert len(externos.docs) == 2


def test_foto_con_sha256_que_no_coincide_es_422(cliente, externos):
    cuerpo = _yape()
    cuerpo["imagen"]["sha256"] = "0" * 64

    respuesta = _enviar(cliente, cuerpo)

    assert respuesta.status_code == 422
    assert externos.docs == []


def test_sin_foto_tambien_se_registra(cliente, externos):
    cuerpo = _yape()
    del cuerpo["imagen"]["contenido_base64"]

    respuesta = _enviar(cliente, cuerpo)

    assert respuesta.status_code == 201
    assert externos.docs[0]["imagen"]["archivo"] is None


def test_recibir_sin_clave_es_401(cliente):
    respuesta = cliente.post(f"/empresas/{RUC}/comprobantes-externos", json=_yape())
    assert respuesta.status_code == 401


# --- Lectura -----------------------------------------------------------------


def test_listar_devuelve_solo_los_de_la_empresa(cliente):
    _enviar(cliente, _yape())
    _enviar(cliente, _yape(), ruc=OTRO_RUC)

    respuesta = cliente.get(f"/empresas/{RUC}/comprobantes-externos?libro=ventas")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["periodos"] == ["202609"]
    [fila] = cuerpo["items"]
    assert fila["fuente"] == "yape"
    assert fila["total"] == "150.00"
    assert fila["fecha_operacion"] == "2026-09-19"
    assert fila["contraparte"]["nombre"] == "JUAN PEREZ"
    assert fila["tiene_imagen"] is True


def test_listar_con_periodo_mal_formado_es_422(cliente):
    assert cliente.get(f"/empresas/{RUC}/comprobantes-externos?periodo=2026-09").status_code == 422


def test_el_bot_puede_leer_un_comprobante_por_id(cliente):
    creado = _enviar(cliente, _yape()).json()

    respuesta = cliente.get(f"/empresas/{RUC}/comprobantes-externos/{creado['id']}", headers=BOT)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    for campo in ("id", "ruc", "periodo", "estado", "creado_en"):
        assert cuerpo[campo] == creado[campo]


def test_la_foto_se_sirve_con_su_tipo(cliente):
    creado = _enviar(cliente, _yape()).json()

    respuesta = cliente.get(f"/empresas/{RUC}/comprobantes-externos/{creado['id']}/imagen")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/jpeg"
    assert respuesta.content == FOTO


def test_la_foto_de_otra_empresa_no_se_sirve(cliente):
    creado = _enviar(cliente, _yape()).json()

    respuesta = cliente.get(f"/empresas/{OTRO_RUC}/comprobantes-externos/{creado['id']}/imagen")

    assert respuesta.status_code == 404
