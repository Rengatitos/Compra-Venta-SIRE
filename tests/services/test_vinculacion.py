"""Códigos de vinculación: el panel los genera, sire-bot los canjea una sola vez."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.api.v1 import deps
from app.api.v1.routes import vinculacion as ruta
from app.core.auth import usuario_actual
from app.core.config import settings
from app.db.database import get_db
from app.services import vinculacion_service

CLAVE = "clave-del-bot-para-pruebas"
RUC = "20603391692"
EMPRESA = {"_id": "65f000000000000000000001", "ruc": RUC, "nombre": "BODEGA LA ESQUINA S.A.C."}
BOT = {"X-Api-Key": CLAVE}


class CodigosFalsos:
    """Imita `app.repositories.codigos_vinculacion` en memoria."""

    def __init__(self):
        self.docs: list[dict] = []

    async def invalidar_activos(self, _db, ruc):
        antes = len(self.docs)
        self.docs = [d for d in self.docs if not (d["ruc"] == ruc and d["usado_en"] is None)]
        return antes - len(self.docs)

    async def crear(self, _db, documento):
        if any(
            d["ruc"] == documento["ruc"] and d["codigo_hash"] == documento["codigo_hash"]
            for d in self.docs
        ):
            raise DuplicateKeyError("uniq_ruc_codigo")
        self.docs.append(dict(documento))

    async def canjear(self, _db, ruc, codigo_hash, dispositivo_id, ahora):
        for d in self.docs:
            if (
                d["ruc"] == ruc
                and d["codigo_hash"] == codigo_hash
                and d["usado_en"] is None
                and d["expira_en"] > ahora
            ):
                d["usado_en"] = ahora
                d["dispositivo_id"] = dispositivo_id
                return d
        return None

    async def buscar(self, _db, ruc, codigo_hash):
        return next(
            (d for d in self.docs if d["ruc"] == ruc and d["codigo_hash"] == codigo_hash), None
        )


@pytest.fixture
def codigos(monkeypatch):
    falsos = CodigosFalsos()
    monkeypatch.setattr(vinculacion_service, "repo_codigos", falsos)
    return falsos


@pytest.fixture
def cliente(monkeypatch, codigos):
    monkeypatch.setattr(settings, "SIRE_BOT_API_KEY", CLAVE)
    empresas = {RUC: EMPRESA, "20111111111": {"_id": "e2", "ruc": "20111111111"}}
    monkeypatch.setattr(
        deps.repo_empresas,
        "obtener_por_ruc",
        AsyncMock(side_effect=lambda _db, ruc: empresas.get(ruc)),
    )
    ruta.limiter.reset()

    app = FastAPI()
    app.state.limiter = ruta.limiter
    app.include_router(ruta.router, prefix="/empresas/{ruc}/codigos-vinculacion")
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[usuario_actual] = lambda: {"email": "prueba@example.com"}
    return TestClient(app)


def _generar(cliente, ruc=RUC) -> str:
    respuesta = cliente.post(f"/empresas/{ruc}/codigos-vinculacion")
    assert respuesta.status_code == 201
    return respuesta.json()["codigo"]


def _canjear(cliente, codigo, ruc=RUC):
    return cliente.post(
        f"/empresas/{ruc}/codigos-vinculacion/canjear",
        json={"codigo": codigo, "dispositivo_id": "web-123"},
        headers=BOT,
    )


def test_generar_devuelve_seis_digitos_y_guarda_solo_el_hash(cliente, codigos):
    respuesta = cliente.post(f"/empresas/{RUC}/codigos-vinculacion")

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert len(cuerpo["codigo"]) == 6 and cuerpo["codigo"].isdigit()
    expira = datetime.fromisoformat(cuerpo["expira_en"].replace("Z", "+00:00"))
    assert timedelta(minutes=9) < expira - datetime.now(UTC) <= timedelta(minutes=10)

    [guardado] = codigos.docs
    assert cuerpo["codigo"] not in str(guardado)
    assert guardado["codigo_hash"] == vinculacion_service.hash_codigo(cuerpo["codigo"])
    assert guardado["creado_por"] == "prueba@example.com"


def test_canjear_un_codigo_valido_devuelve_la_empresa(cliente, codigos):
    codigo = _generar(cliente)

    respuesta = _canjear(cliente, codigo)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"empresa": {"ruc": RUC, "nombre": "BODEGA LA ESQUINA S.A.C."}}
    assert codigos.docs[0]["dispositivo_id"] == "web-123"


def test_un_codigo_solo_sirve_una_vez(cliente):
    codigo = _generar(cliente)
    assert _canjear(cliente, codigo).status_code == 200

    segunda = _canjear(cliente, codigo)

    assert segunda.status_code == 409


def test_codigo_desconocido_o_mal_formado_es_400(cliente):
    assert _canjear(cliente, "000000").status_code == 400
    assert _canjear(cliente, "12ab").status_code == 400


def test_codigo_vencido_es_400(cliente, codigos):
    hace_rato = datetime.now(UTC) - timedelta(minutes=11)
    resultado = asyncio.run(
        vinculacion_service.generar(None, EMPRESA, "prueba@example.com", ahora=hace_rato)
    )

    assert _canjear(cliente, resultado["codigo"]).status_code == 400


def test_generar_otro_anula_el_anterior(cliente):
    primero = _generar(cliente)
    segundo = _generar(cliente)

    if primero != segundo:
        assert _canjear(cliente, primero).status_code == 400
    assert _canjear(cliente, segundo).status_code == 200


def test_el_codigo_de_una_empresa_no_sirve_para_otra(cliente):
    codigo = _generar(cliente)

    assert _canjear(cliente, codigo, ruc="20111111111").status_code == 400


def test_ruc_no_registrado_es_404(cliente):
    assert _canjear(cliente, "123456", ruc="20999999999").status_code == 404


def test_canje_exige_la_clave_del_bot(cliente):
    codigo = _generar(cliente)
    respuesta = cliente.post(
        f"/empresas/{RUC}/codigos-vinculacion/canjear",
        json={"codigo": codigo, "dispositivo_id": "web-123"},
    )
    assert respuesta.status_code == 401


def test_empresa_sin_nombre_usa_el_ruc():
    assert vinculacion_service.nombre_de({"ruc": RUC}) == f"RUC {RUC}"
    assert vinculacion_service.nombre_de({"ruc": RUC, "nombre": "  "}) == f"RUC {RUC}"
