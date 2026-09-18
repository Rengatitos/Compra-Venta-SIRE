"""Login con Google, sin red y sin Mongo.

La verificación del ID token contra Google se simula: lo que se comprueba aquí
es lo que hace la ruta con cada resultado posible, que es donde están las
decisiones (401 frente a 403 frente a 503).
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import auth as ruta_auth
from app.core.auth import decode_token
from app.core.config import settings
from app.services import google_oauth

AUTORIZADO = "espinozavaleracinver@gmail.com"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_EMAILS", [AUTORIZADO])
    app = FastAPI()
    app.include_router(ruta_auth.router, prefix="/auth")
    # slowapi resuelve el limiter en request.app.state.
    app.state.limiter = ruta_auth.limiter
    return TestClient(app)


def _google_devuelve(monkeypatch, **datos):
    monkeypatch.setattr(
        ruta_auth.google_oauth,
        "verificar_id_token",
        AsyncMock(return_value={"email": AUTORIZADO, "nombre": "Cinver", "foto": None} | datos),
    )


def test_correo_autorizado_recibe_un_token_de_persona(cliente, monkeypatch):
    _google_devuelve(monkeypatch)

    respuesta = cliente.post("/auth/google", json={"credential": "id-token-de-google"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["usuario"]["email"] == AUTORIZADO
    # El perfil viaja en el cuerpo para que el panel no tenga que abrir el JWT.
    assert cuerpo["usuario"]["nombre"] == "Cinver"

    payload = decode_token(cuerpo["access_token"])
    assert payload["tipo"] == "usuario"
    assert payload["email"] == AUTORIZADO


def test_correo_fuera_de_la_allowlist_recibe_403(cliente, monkeypatch):
    _google_devuelve(monkeypatch, email="ajeno@gmail.com")

    respuesta = cliente.post("/auth/google", json={"credential": "id-token-de-google"})

    # 403 y no 401: la cuenta es auténtica, lo que falta es la autorización.
    assert respuesta.status_code == 403
    # El mensaje no dice si esa cuenta existe ni quién sí tiene acceso.
    assert "ajeno@gmail.com" not in respuesta.text


def test_token_de_google_invalido_recibe_401(cliente, monkeypatch):
    monkeypatch.setattr(
        ruta_auth.google_oauth,
        "verificar_id_token",
        AsyncMock(side_effect=google_oauth.ErrorIdTokenGoogle("firma inválida")),
    )

    respuesta = cliente.post("/auth/google", json={"credential": "falso"})

    assert respuesta.status_code == 401


def test_google_inalcanzable_recibe_503_y_no_401(cliente, monkeypatch):
    # Si se confundiera con un 401, una caída de Google se leería en los logs
    # como una oleada de intentos de acceso con tokens falsos.
    monkeypatch.setattr(
        ruta_auth.google_oauth,
        "verificar_id_token",
        AsyncMock(side_effect=google_oauth.ErrorRedGoogle("timeout del JWKS")),
    )

    respuesta = cliente.post("/auth/google", json={"credential": "id-token-de-google"})

    assert respuesta.status_code == 503


def test_una_credencial_malformada_es_401_y_no_un_500(monkeypatch):
    # `get_signing_key_from_jwt` ya lee la cabecera del token, así que una
    # cadena que no es un JWT revienta ahí con DecodeError. Sin capturarlo, el
    # cliente veía un 500 —que parece un fallo del servidor— en vez del 401 que
    # corresponde a una credencial inservible.
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "cliente.apps.googleusercontent.com")

    with pytest.raises(google_oauth.ErrorIdTokenGoogle):
        google_oauth._verificar("esto-no-es-un-jwt")


def test_sin_client_id_no_se_valida_la_audiencia_a_la_ligera(monkeypatch):
    # El guard del servicio: sin GOOGLE_CLIENT_ID no se puede seguir, porque
    # `jwt.decode(audience=None)` se saltaría la comprobación de `aud` y dejaría
    # entrar un ID token emitido para cualquier otra aplicación de Google.
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)

    with pytest.raises(google_oauth.ErrorIdTokenGoogle):
        google_oauth._verificar("lo-que-sea")
