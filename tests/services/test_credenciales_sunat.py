"""Credenciales de API SUNAT obtenidas desde el menú SOL, sin teclearlas."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import deps
from app.api.v1.routes import empresas as ruta
from app.core.auth import usuario_actual
from app.core.encryption import encrypt_password
from app.db.database import get_db
from app.services import credenciales_sunat_service as servicio
from app.services.scraping_sunat import CredencialesSolError
from app.services.sunat import credenciales_api
from app.services.sunat.credenciales_api import AplicacionSunat, SinRecursoSire

RUC = "10209911031"
RESPUESTA_SUNAT = {
    "id": "68c1969c8165197203fe1517",
    "numRuc": RUC,
    "nomApp": "SMARTSIRE",
    "desClientId": "90a5fdc6-0999-4753-9e7c-eb507620513a",
    "desClientSecret": "clave-de-prueba==",
    "expFlujoAutoriz": "100000",
    "apis": [
        {"codApi": "0", "recursos": [{"desPathRecurso": "/v1/contribuyente/controlcpe"}]},
        {"codApi": "1", "recursos": [{"desPathRecurso": "/v1/contribuyente/migeigv"}]},
    ],
}
APP = AplicacionSunat(
    nombre="SMARTSIRE",
    client_id="90a5fdc6-0999-4753-9e7c-eb507620513a",
    client_secret="clave-de-prueba==",
    recursos=("/v1/contribuyente/migeigv",),
)


def _empresa() -> dict:
    return {"_id": "e1", "ruc": RUC, "usuario": "LEEINTUN", "password": encrypt_password("x")}


# --- Lectura de la respuesta de SUNAT ------------------------------------------


def test_lee_la_aplicacion_y_sus_recursos():
    app = credenciales_api._desde_api(RESPUESTA_SUNAT)
    assert app is not None
    assert app.client_id == RESPUESTA_SUNAT["desClientId"]
    assert app.client_secret == "clave-de-prueba=="
    assert app.tiene_sire


@pytest.mark.parametrize("vacia", [None, "", {}, {"nomApp": "X"}, []])
def test_sin_aplicacion_es_none(vacia):
    assert credenciales_api._desde_api(vacia) is None


def test_sin_recurso_sire():
    sin_sire = {**RESPUESTA_SUNAT, "apis": RESPUESTA_SUNAT["apis"][:1]}
    assert not credenciales_api._desde_api(sin_sire).tiene_sire


def test_la_clave_no_aparece_en_repr():
    assert "clave-de-prueba" not in repr(APP)


def test_registrar_pide_acceso_a_sire(monkeypatch):
    llamadas = []

    def falso(metodo, token, cuerpo=None):
        llamadas.append((metodo, cuerpo))
        return RESPUESTA_SUNAT if metodo == "GET" else None

    monkeypatch.setattr(credenciales_api, "_llamar", falso)
    app = credenciales_api.registrar("tk", "SIRE APACLLA", "https://www.apaclla.com")
    metodo, cuerpo = llamadas[0]
    assert metodo == "POST"
    assert cuerpo["recursos"] == [{"desPathRecurso": "/v1/contribuyente/migeigv"}]
    assert cuerpo["nomApp"] == "SIRE APACLLA"
    assert cuerpo["id"] is None
    assert app.client_id == RESPUESTA_SUNAT["desClientId"]


def test_obtener_no_toca_una_aplicacion_sin_sire(monkeypatch):
    monkeypatch.setattr(credenciales_api, "token_de_sesion", lambda *a, **k: "tk")
    sin_sire = AplicacionSunat("OTRA", "id", "clave", ("/v1/contribuyente/gre",))
    monkeypatch.setattr(credenciales_api, "leer", lambda token: sin_sire)
    registrar = pytest.fail  # no debe llamarse
    monkeypatch.setattr(credenciales_api, "registrar", registrar)
    with pytest.raises(SinRecursoSire):
        credenciales_api.obtener(RUC, "U", "P", crear_con=("SIRE APACLLA", "https://x.pe"))


def test_obtener_registra_si_no_hay(monkeypatch):
    monkeypatch.setattr(credenciales_api, "token_de_sesion", lambda *a, **k: "tk")
    monkeypatch.setattr(credenciales_api, "leer", lambda token: None)
    monkeypatch.setattr(credenciales_api, "registrar", lambda token, nombre, url: APP)
    assert credenciales_api.obtener(RUC, "U", "P", crear_con=("N", "https://x.pe")) == (APP, True)


# --- Servicio: guarda en la empresa y no devuelve la clave ---------------------


@pytest.fixture
def repo(monkeypatch):
    actualizar = AsyncMock()
    monkeypatch.setattr(servicio.repo_empresas, "actualizar", actualizar)
    return actualizar


@pytest.mark.parametrize(
    ("creada", "token", "origen"),
    [(False, "tk", "existente"), (True, "tk", "creada"), (True, None, "creada")],
)
def test_servicio_guarda_y_resume(monkeypatch, repo, creada, token, origen):
    monkeypatch.setattr(servicio.credenciales_api, "obtener", lambda *a, **k: (APP, creada))
    monkeypatch.setattr(servicio, "obtener_token", AsyncMock(return_value=(token, None)))

    resumen = asyncio.run(servicio.obtener(object(), _empresa()))

    guardado = repo.await_args.args[2]
    assert guardado["sunat_client_id"] == APP.client_id
    assert guardado["sunat_client_secret"] == APP.client_secret
    assert guardado["sunat_token"] == token
    assert resumen["origen"] == origen
    assert resumen["token_valido"] is bool(token)
    assert "clave-de-prueba" not in str(resumen)
    assert resumen["client_id"] == "90a5fdc6…"


# --- Ruta ----------------------------------------------------------------------


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(deps.repo_empresas, "obtener_por_ruc", AsyncMock(return_value=_empresa()))
    ruta.limiter.reset()
    app = FastAPI()
    app.state.limiter = ruta.limiter
    app.include_router(ruta.router, prefix="/empresas")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[usuario_actual] = lambda: {"email": "a@b.pe", "rol": "admin"}
    return TestClient(app)


def test_ruta_devuelve_el_resumen(cliente, monkeypatch):
    resumen = {
        "origen": "existente",
        "aplicacion": "SMARTSIRE",
        "client_id": "90a5fdc6…",
        "token_valido": True,
        "mensaje": "ok",
    }
    monkeypatch.setattr(servicio, "obtener", AsyncMock(return_value=resumen))
    r = cliente.post(f"/empresas/{RUC}/credenciales-sunat")
    assert r.status_code == 200
    assert r.json() == resumen


@pytest.mark.parametrize(
    ("error", "codigo"),
    [
        (CredencialesSolError("mal"), 400),
        (SinRecursoSire("sin SIRE"), 409),
        (credenciales_api.CredencialesApiError("caído"), 502),
    ],
)
def test_ruta_traduce_los_errores(cliente, monkeypatch, error, codigo):
    monkeypatch.setattr(servicio, "obtener", AsyncMock(side_effect=error))
    assert cliente.post(f"/empresas/{RUC}/credenciales-sunat").status_code == codigo
