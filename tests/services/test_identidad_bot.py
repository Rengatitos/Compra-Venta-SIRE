"""Canal de WhatsApp: el bot identifica la empresa por RUC y usuario SOL."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import deps
from app.api.v1.routes import identidad_bot as ruta
from app.core.config import settings
from app.db.database import get_db

CLAVE = "clave-del-bot-para-pruebas"
BOT = {"X-Api-Key": CLAVE}
CON_NOMBRE = "20602621597"
SIN_NOMBRE = "10209911031"
EMPRESAS = {
    CON_NOMBRE: {
        "ruc": CON_NOMBRE,
        "usuario": "EEDIPTIO",
        "ficha_ruc": {"razon_social": "INVERSIONES GUADALUPE & PEÑA S.A.C."},
    },
    SIN_NOMBRE: {"ruc": SIN_NOMBRE, "usuario": "LEEINTUN"},
}


@pytest.fixture
def ficha(monkeypatch):
    obtener = AsyncMock(return_value=SimpleNamespace(razon_social="ARAUCO CASTILLO PEPE"))
    monkeypatch.setattr(ruta.ficha_ruc_service, "obtener", obtener)
    return obtener


@pytest.fixture
def cliente(monkeypatch, ficha):
    monkeypatch.setattr(settings, "SIRE_BOT_API_KEY", CLAVE)
    monkeypatch.setattr(
        deps.repo_empresas,
        "obtener_por_ruc",
        AsyncMock(side_effect=lambda _db, ruc: EMPRESAS.get(ruc)),
    )
    ruta.limiter.reset()
    app = FastAPI()
    app.state.limiter = ruta.limiter
    app.include_router(ruta.router, prefix="/empresas/{ruc}/bot")
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def test_identidad_usa_la_razon_social_guardada(cliente, ficha):
    r = cliente.get(f"/empresas/{CON_NOMBRE}/bot/identidad", headers=BOT)
    assert r.status_code == 200
    assert r.json() == {"ruc": CON_NOMBRE, "razon_social": "INVERSIONES GUADALUPE & PEÑA S.A.C."}
    ficha.assert_not_awaited()


def test_identidad_consulta_la_ficha_si_no_hay_nombre(cliente, ficha):
    r = cliente.get(f"/empresas/{SIN_NOMBRE}/bot/identidad", headers=BOT)
    assert r.json()["razon_social"] == "ARAUCO CASTILLO PEPE"
    ficha.assert_awaited_once()


def test_identidad_sin_ficha_devuelve_nombre_nulo(cliente, ficha):
    ficha.side_effect = RuntimeError("SUNAT caído")
    r = cliente.get(f"/empresas/{SIN_NOMBRE}/bot/identidad", headers=BOT)
    assert r.status_code == 200
    assert r.json()["razon_social"] is None


def test_identidad_ruc_no_registrado_es_404(cliente):
    r = cliente.get("/empresas/20999999999/bot/identidad", headers=BOT)
    assert r.status_code == 404


def test_identidad_sin_clave_no_pasa(cliente):
    assert cliente.get(f"/empresas/{CON_NOMBRE}/bot/identidad").status_code == 401
    r = cliente.get(f"/empresas/{CON_NOMBRE}/bot/identidad", headers={"X-Api-Key": "otra"})
    assert r.status_code == 403


@pytest.mark.parametrize("usuario", ["LEEINTUN", "leeintun", "  LeeIntun "])
def test_usuario_correcto_sin_importar_mayusculas(cliente, usuario):
    r = cliente.post(
        f"/empresas/{SIN_NOMBRE}/bot/verificar-usuario", json={"usuario": usuario}, headers=BOT
    )
    assert r.status_code == 200
    assert r.json() == {"empresa": {"ruc": SIN_NOMBRE, "nombre": "ARAUCO CASTILLO PEPE"}}


def test_usuario_incorrecto_es_400_y_no_revela_el_correcto(cliente):
    r = cliente.post(
        f"/empresas/{SIN_NOMBRE}/bot/verificar-usuario", json={"usuario": "OTRO"}, headers=BOT
    )
    assert r.status_code == 400
    assert "LEEINTUN" not in r.text


def test_empresa_sin_usuario_sol_nunca_coincide(cliente, monkeypatch):
    EMPRESAS["20111111111"] = {"ruc": "20111111111"}
    try:
        r = cliente.post(
            "/empresas/20111111111/bot/verificar-usuario", json={"usuario": " "}, headers=BOT
        )
        assert r.status_code in (400, 422)
    finally:
        del EMPRESAS["20111111111"]


def test_intentos_limitados_por_empresa(cliente):
    codigos = [
        cliente.post(
            f"/empresas/{SIN_NOMBRE}/bot/verificar-usuario", json={"usuario": "X"}, headers=BOT
        ).status_code
        for _ in range(11)
    ]
    assert codigos[-1] == 429
