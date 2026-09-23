"""Roles del panel: administradores fijos del entorno y correos agregados desde la web."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import usuarios as rutas
from app.core.auth import create_token
from app.core.config import settings
from app.db.database import get_db
from app.domain.usuario import Rol, resolver_rol

FIJO = "puff27oo@gmail.com"


class TestResolverRol:
    def test_el_admin_fijo_es_admin_aunque_figure_como_usuario(self):
        assert resolver_rol("PUFF27OO@gmail.com", [FIJO], "usuario") is Rol.ADMIN

    def test_un_registrado_entra_con_su_rol(self):
        assert resolver_rol("ana@x.pe", [FIJO], "usuario") is Rol.USUARIO
        assert resolver_rol("ana@x.pe", [FIJO], "admin") is Rol.ADMIN

    def test_sin_registro_ni_lista_no_entra(self):
        assert resolver_rol("ana@x.pe", [FIJO], None) is None
        assert resolver_rol("", [FIJO], "admin") is None
        assert resolver_rol("ana@x.pe", [FIJO], "superusuario") is None


class RepoEnMemoria:
    def __init__(self):
        self.datos: dict[str, dict] = {}

    async def rol_de(self, db, correo):
        return (self.datos.get(correo.lower()) or {}).get("rol")

    async def listar(self, db):
        return list(self.datos.values())

    async def guardar(self, db, correo, rol, por):
        self.datos[correo] = {"email": correo, "rol": rol.value, "agregado_por": por}
        return self.datos[correo]

    async def eliminar(self, db, correo):
        return self.datos.pop(correo, None) is not None


@pytest.fixture
def repo(monkeypatch):
    repo = RepoEnMemoria()
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_EMAILS", [FIJO])
    for nombre in ("rol_de", "listar", "guardar", "eliminar"):
        monkeypatch.setattr(rutas.repo_usuarios, nombre, getattr(repo, nombre))
    return repo


@pytest.fixture
def cliente(repo):
    app = FastAPI()
    app.include_router(rutas.router, prefix="/usuarios")
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def _como(correo: str) -> dict:
    return {"Authorization": f"Bearer {create_token(correo)}"}


def test_un_admin_fijo_agrega_usuarios_y_los_ve_en_la_lista(cliente):
    alta = cliente.post("/usuarios", json={"email": " Ana@Empresa.pe ", "rol": "usuario"},
                        headers=_como(FIJO))
    assert alta.status_code == 201
    assert alta.json()["email"] == "ana@empresa.pe"

    lista = cliente.get("/usuarios", headers=_como(FIJO)).json()
    assert [(u["email"], u["rol"], u["fijo"]) for u in lista] == [
        (FIJO, "admin", True), ("ana@empresa.pe", "usuario", False),
    ]


def test_un_usuario_normal_no_gestiona_accesos(cliente, repo):
    repo.datos["ana@empresa.pe"] = {"email": "ana@empresa.pe", "rol": "usuario"}
    assert cliente.get("/usuarios", headers=_como("ana@empresa.pe")).status_code == 403
    assert cliente.post("/usuarios", json={"email": "otro@x.pe"},
                        headers=_como("ana@empresa.pe")).status_code == 403


def test_un_admin_agregado_desde_la_web_tambien_gestiona(cliente, repo):
    repo.datos["jefe@x.pe"] = {"email": "jefe@x.pe", "rol": "admin"}
    assert cliente.post("/usuarios", json={"email": "otro@x.pe"},
                        headers=_como("jefe@x.pe")).status_code == 201


def test_los_admins_fijos_no_se_tocan_desde_la_web(cliente):
    assert cliente.delete(f"/usuarios/{FIJO}", headers=_como(FIJO)).status_code == 409
    assert cliente.patch(f"/usuarios/{FIJO}", json={"rol": "usuario"},
                         headers=_como(FIJO)).status_code == 409


def test_nadie_se_quita_a_si_mismo(cliente, repo):
    repo.datos["jefe@x.pe"] = {"email": "jefe@x.pe", "rol": "admin"}
    assert cliente.delete("/usuarios/jefe@x.pe", headers=_como("jefe@x.pe")).status_code == 409
    assert cliente.patch("/usuarios/jefe@x.pe", json={"rol": "usuario"},
                         headers=_como("jefe@x.pe")).status_code == 409


def test_quitar_el_acceso_lo_expulsa_en_la_siguiente_peticion(cliente, repo):
    repo.datos["ana@empresa.pe"] = {"email": "ana@empresa.pe", "rol": "admin"}
    assert cliente.get("/usuarios", headers=_como("ana@empresa.pe")).status_code == 200
    assert cliente.delete("/usuarios/ana@empresa.pe", headers=_como(FIJO)).status_code == 204
    assert cliente.get("/usuarios", headers=_como("ana@empresa.pe")).status_code == 403


def test_un_correo_mal_escrito_se_rechaza(cliente):
    assert cliente.post("/usuarios", json={"email": "sin-arroba"},
                        headers=_como(FIJO)).status_code == 422
