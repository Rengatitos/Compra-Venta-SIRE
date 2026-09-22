"""Autenticación de servicio de sire-bot: `X-Api-Key` contra `SIRE_BOT_API_KEY`."""

from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import deps
from app.core.auth import create_token
from app.core.config import settings
from app.core.servicio import bot_autorizado
from app.db.database import get_db

CLAVE = "clave-del-bot-para-pruebas"
RUC = "20603391692"
AUTORIZADO = "prueba@example.com"


@pytest.fixture(autouse=True)
def configuracion(monkeypatch):
    monkeypatch.setattr(settings, "SIRE_BOT_API_KEY", CLAVE)
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_EMAILS", [AUTORIZADO])
    monkeypatch.setattr(
        deps.repo_empresas,
        "obtener_por_ruc",
        AsyncMock(side_effect=lambda _db, ruc: {"_id": "e1", "ruc": ruc} if ruc == RUC else None),
    )


@pytest.fixture
def cliente():
    app = FastAPI()

    @app.get("/bot")
    async def solo_bot(_bot: None = Depends(bot_autorizado)):
        return {"ok": True}

    @app.get("/empresas/{ruc}/bot")
    async def empresa_bot(empresa: dict = Depends(deps.empresa_para_bot)):
        return {"ruc": empresa["ruc"]}

    @app.get("/empresas/{ruc}/mixto")
    async def mixto(empresa: dict = Depends(deps.empresa_para_usuario_o_bot)):
        return {"ruc": empresa["ruc"]}

    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_clave_correcta_pasa(cliente):
    assert cliente.get("/bot", headers={"X-Api-Key": CLAVE}).status_code == 200


def test_sin_cabecera_es_401(cliente):
    assert cliente.get("/bot").status_code == 401


def test_clave_incorrecta_es_403(cliente):
    assert cliente.get("/bot", headers={"X-Api-Key": "otra"}).status_code == 403


def test_sin_clave_configurada_falla_cerrado(cliente, monkeypatch):
    monkeypatch.setattr(settings, "SIRE_BOT_API_KEY", None)
    respuesta = cliente.get("/bot", headers={"X-Api-Key": CLAVE})
    assert respuesta.status_code == 503


def test_empresa_para_bot_resuelve_el_ruc(cliente):
    ok = cliente.get(f"/empresas/{RUC}/bot", headers={"X-Api-Key": CLAVE})
    assert ok.json() == {"ruc": RUC}
    otro = cliente.get("/empresas/20000000000/bot", headers={"X-Api-Key": CLAVE})
    assert otro.status_code == 404


def test_mixto_acepta_la_sesion_del_panel(cliente):
    token = create_token(AUTORIZADO)
    respuesta = cliente.get(f"/empresas/{RUC}/mixto", headers={"Authorization": f"Bearer {token}"})
    assert respuesta.status_code == 200


def test_mixto_acepta_al_bot(cliente):
    respuesta = cliente.get(f"/empresas/{RUC}/mixto", headers={"X-Api-Key": CLAVE})
    assert respuesta.status_code == 200


def test_mixto_con_clave_mala_no_cae_al_jwt(cliente):
    token = create_token(AUTORIZADO)
    respuesta = cliente.get(
        f"/empresas/{RUC}/mixto",
        headers={"X-Api-Key": "otra", "Authorization": f"Bearer {token}"},
    )
    assert respuesta.status_code == 403


def test_mixto_sin_nada_es_401(cliente):
    assert cliente.get(f"/empresas/{RUC}/mixto").status_code == 401
