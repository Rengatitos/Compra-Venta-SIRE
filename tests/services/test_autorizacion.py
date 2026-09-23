"""Las dos dependencias que sostienen el modelo de autorización.

`usuario_actual` dice quién pregunta; `empresa_actual` dice sobre qué empresa.
Antes las dos salían del mismo token y tenían que coincidir; ahora el token solo
aporta el permiso y la empresa se resuelve por el RUC del path.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import deps
from app.core.auth import create_token, usuario_actual
from app.core.config import settings
from app.db.database import get_db

AUTORIZADO = "espinozavaleracinver@gmail.com"
RUC = "20603391692"


@pytest.fixture(autouse=True)
def allowlist(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_EMAILS", [AUTORIZADO])


@pytest.fixture
def cliente():
    """App de juguete con las dos dependencias montadas tal como en producción."""
    app = FastAPI()

    @app.get("/yo")
    async def yo(usuario: dict = Depends(usuario_actual)):
        return usuario

    @app.get("/empresas/{ruc}/ping")
    async def ping(empresa: dict = Depends(deps.empresa_actual)):
        return {"ruc": empresa["ruc"]}

    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def _cabecera(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_token_valido_identifica_a_la_persona(cliente):
    respuesta = cliente.get("/yo", headers=_cabecera(create_token(AUTORIZADO)))

    assert respuesta.status_code == 200
    assert respuesta.json() == {"email": AUTORIZADO, "rol": "admin"}


def test_el_correo_se_normaliza_al_entrar(cliente):
    respuesta = cliente.get("/yo", headers=_cabecera(create_token("Espinoza" + AUTORIZADO[8:])))

    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == AUTORIZADO


def test_sin_cabecera_es_401(cliente):
    assert cliente.get("/yo").status_code == 401


def test_token_expirado_es_401(cliente):
    expirado = jwt.encode(
        {
            "tipo": "usuario",
            "sub": AUTORIZADO,
            "email": AUTORIZADO,
            "exp": datetime.now(UTC) - timedelta(hours=1),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    respuesta = cliente.get("/yo", headers=_cabecera(expirado))

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Token expirado"


def test_token_del_esquema_anterior_es_401(cliente):
    """Un JWT de empresa, firmado con el mismo secreto, ya no sirve.

    Es la garantía de que el cambio de esquema invalida las sesiones vivas sin
    tener que rotar `JWT_SECRET_KEY`, que además de esto dejaría ilegibles las
    contraseñas SOL cifradas (ver el comentario de `app.core.auth`).
    """
    antiguo = jwt.encode(
        {
            "empresa_id": "664b0f2e1c2d4a0001aa0001",
            "ruc": RUC,
            "exp": datetime.now(UTC) + timedelta(hours=2),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    respuesta = cliente.get("/yo", headers=_cabecera(antiguo))

    assert respuesta.status_code == 401
    assert "anterior" in respuesta.json()["detail"]


def test_correo_retirado_de_la_allowlist_es_403(cliente, monkeypatch):
    # El token sigue siendo válido: la allowlist se revalida en cada petición
    # precisamente para no tener que esperar a que caduque.
    token = create_token(AUTORIZADO)
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_EMAILS", [])

    respuesta = cliente.get("/yo", headers=_cabecera(token))

    assert respuesta.status_code == 403


def test_empresa_actual_resuelve_por_el_ruc_del_path(cliente, monkeypatch):
    monkeypatch.setattr(
        deps.repo_empresas,
        "obtener_por_ruc",
        AsyncMock(return_value={"_id": "empresa", "ruc": RUC}),
    )

    respuesta = cliente.get(f"/empresas/{RUC}/ping", headers=_cabecera(create_token(AUTORIZADO)))

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ruc": RUC}


def test_empresa_actual_con_ruc_inexistente_es_404(cliente, monkeypatch):
    # Antes esto era un 403 ("el token no corresponde a esta empresa"). Con una
    # sesión por persona, pedir una empresa que no existe es sencillamente eso.
    monkeypatch.setattr(deps.repo_empresas, "obtener_por_ruc", AsyncMock(return_value=None))

    respuesta = cliente.get(
        "/empresas/20000000000/ping", headers=_cabecera(create_token(AUTORIZADO))
    )

    assert respuesta.status_code == 404


def test_empresa_actual_exige_sesion_antes_de_tocar_mongo(cliente, monkeypatch):
    buscar = AsyncMock(return_value={"_id": "empresa", "ruc": RUC})
    monkeypatch.setattr(deps.repo_empresas, "obtener_por_ruc", buscar)

    respuesta = cliente.get(f"/empresas/{RUC}/ping")

    assert respuesta.status_code == 401
    buscar.assert_not_called()
