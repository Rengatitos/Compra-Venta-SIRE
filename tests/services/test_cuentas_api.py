"""Cuentas de API: integraciones que entran con correo y contraseña, sin Google."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import auth as ruta_auth
from app.api.v1.routes import cuentas_api as ruta_cuentas
from app.core import auth as core_auth
from app.core import claves
from app.core.auth import decode_token, exigir_admin
from app.core.config import settings
from app.db.database import get_db
from app.domain.usuario import Rol
from app.repositories import cuentas_api as repo

CORREO = "administrador@apaclla.au.pe"
ADMIN = {"email": "puff27oo@gmail.com", "rol": "admin"}


class Coleccion:
    """Imita la colección `cuentas_api` lo justo para el repositorio."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    async def find_one(self, filtro, proyeccion=None):
        doc = self.docs.get(filtro["email"])
        if doc is None:
            return None
        if proyeccion and proyeccion.get("clave_hash") == 0:
            return {k: v for k, v in doc.items() if k != "clave_hash"}
        return dict(doc)

    async def update_one(self, filtro, cambios, upsert=False):
        doc = self.docs.get(filtro["email"])
        if doc is None:
            if not upsert:
                return
            doc = {**cambios.get("$setOnInsert", {})}
        doc.update(cambios.get("$set", {}))
        self.docs[filtro["email"]] = doc

    async def delete_one(self, filtro):
        existia = self.docs.pop(filtro["email"], None) is not None
        return type("R", (), {"deleted_count": int(existia)})()

    def find(self, *_a, **_k):
        docs = [{k: v for k, v in d.items() if k != "clave_hash"} for d in self.docs.values()]

        class Cursor:
            def sort(self, *_a):
                return self

            async def to_list(self, length=None):
                return docs

        return Cursor()


@pytest.fixture
def coleccion(monkeypatch):
    col = Coleccion()
    monkeypatch.setattr(repo, "_col", lambda db: col)
    return col


@pytest.fixture
def sin_personas(monkeypatch):
    async def ninguno(db, correo):
        return None

    monkeypatch.setattr(core_auth.repo_usuarios, "rol_de", ninguno)
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_EMAILS", [ADMIN["email"]])


@pytest.fixture
def cliente(coleccion, sin_personas):
    ruta_auth.limiter.reset()
    app = FastAPI()
    app.state.limiter = ruta_auth.limiter
    app.include_router(ruta_auth.router, prefix="/auth")
    app.include_router(ruta_cuentas.router, prefix="/cuentas-api")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[exigir_admin] = lambda: ADMIN
    return TestClient(app)


def _crear(cliente, **extra) -> str:
    r = cliente.post("/cuentas-api", json={"email": CORREO, **extra})
    assert r.status_code == 201, r.text
    return r.json()["password"]


# --- Contraseñas ---------------------------------------------------------------


def test_hash_verifica_y_no_guarda_la_clave():
    clave = claves.generar()
    guardado = claves.hashear(clave)
    assert clave not in guardado
    assert claves.verificar(clave, guardado)
    assert not claves.verificar(clave + "x", guardado)
    assert claves.hashear(clave) != guardado  # sal distinta cada vez


def test_claves_generadas_son_largas_y_distintas():
    generadas = {claves.generar() for _ in range(50)}
    assert len(generadas) == 50
    assert all(len(c) >= 32 for c in generadas)


@pytest.mark.parametrize("roto", ["", "bcrypt$x", "scrypt$a$b$c$d$e", "scrypt$16384$8$1$@@$@@"])
def test_hash_roto_no_valida(roto):
    assert not claves.verificar("lo-que-sea", roto)


# --- Login con correo y contraseña ---------------------------------------------


def test_login_devuelve_un_token_de_sesion(cliente):
    clave = _crear(cliente)
    r = cliente.post("/auth/token", json={"email": CORREO.upper(), "password": clave})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["usuario"] == {"email": CORREO, "nombre": None, "foto": None, "rol": "admin"}
    assert decode_token(cuerpo["access_token"])["email"] == CORREO


def test_token_de_cuenta_api_dura_5_horas(cliente, monkeypatch):
    monkeypatch.setattr(settings, "JWT_EXPIRE_HOURS", 2)
    clave = _crear(cliente)
    cuerpo = cliente.post("/auth/token", json={"email": CORREO, "password": clave}).json()
    assert cuerpo["expires_in"] == 5 * 3600
    restante = decode_token(cuerpo["access_token"])["exp"] - datetime.now(UTC).timestamp()
    assert 5 * 3600 - 60 < restante <= 5 * 3600


def test_cuenta_antigua_con_rol_usuario_entra_como_admin(cliente, coleccion):
    clave = _crear(cliente)
    coleccion.docs[CORREO]["rol"] = "usuario"
    assert asyncio.run(core_auth.rol_de(object(), CORREO)) == Rol.ADMIN
    r = cliente.post("/auth/token", json={"email": CORREO, "password": clave})
    assert r.json()["usuario"]["rol"] == "admin"


@pytest.mark.parametrize(
    ("correo", "clave"),
    [(CORREO, "mala"), ("otro@apaclla.au.pe", "mala")],
)
def test_login_rechazado_no_revela_si_la_cuenta_existe(cliente, correo, clave):
    _crear(cliente)
    r = cliente.post("/auth/token", json={"email": correo, "password": clave})
    assert r.status_code == 401
    assert r.json()["detail"] == ruta_auth.CREDENCIALES_MALAS


def test_login_con_clave_vencida(cliente, coleccion):
    clave = _crear(cliente)
    coleccion.docs[CORREO]["expira_en"] = datetime.now(UTC) - timedelta(minutes=1)
    r = cliente.post("/auth/token", json={"email": CORREO, "password": clave})
    assert r.status_code == 401
    assert "venció" in r.json()["detail"]


def test_regenerar_invalida_la_clave_anterior(cliente):
    vieja = _crear(cliente)
    r = cliente.post(f"/cuentas-api/{CORREO}/regenerar", json={})
    nueva = r.json()["password"]
    assert nueva != vieja
    assert cliente.post("/auth/token", json={"email": CORREO, "password": vieja}).status_code == 401
    assert cliente.post("/auth/token", json={"email": CORREO, "password": nueva}).status_code == 200


def test_login_limitado_por_minuto(cliente):
    _crear(cliente)
    codigos = [
        cliente.post("/auth/token", json={"email": CORREO, "password": "x"}).status_code
        for _ in range(6)
    ]
    assert codigos[-1] == 429


# --- El rol se revisa en cada petición -----------------------------------------


def test_rol_de_reconoce_la_cuenta_vigente(cliente, coleccion):
    _crear(cliente)
    assert asyncio.run(core_auth.rol_de(object(), CORREO)) == Rol.ADMIN
    # El login con Google no la acepta aunque exista un buzón con ese nombre.
    assert asyncio.run(core_auth.rol_de(object(), CORREO, cuentas_api=False)) is None
    coleccion.docs[CORREO]["expira_en"] = datetime.now(UTC) - timedelta(seconds=1)
    assert asyncio.run(core_auth.rol_de(object(), CORREO)) is None


def test_eliminarla_corta_el_acceso(cliente):
    _crear(cliente)
    assert cliente.delete(f"/cuentas-api/{CORREO}").status_code == 204
    assert asyncio.run(core_auth.rol_de(object(), CORREO)) is None
    assert cliente.delete(f"/cuentas-api/{CORREO}").status_code == 404


# --- Administración -----------------------------------------------------------


def test_listar_nunca_devuelve_hash_ni_clave(cliente):
    clave = _crear(cliente, vigencia_dias=30)
    r = cliente.get("/cuentas-api")
    assert r.status_code == 200
    [cuenta] = r.json()
    assert cuenta["email"] == CORREO and cuenta["vigente"] and cuenta["vigencia_dias"] == 30
    assert "clave_hash" not in r.text and clave not in r.text


def test_no_se_duplica(cliente):
    _crear(cliente)
    assert cliente.post("/cuentas-api", json={"email": CORREO}).status_code == 409


def test_correo_de_una_persona_puede_tener_cuenta_de_api(cliente, monkeypatch):
    persona = "contadora@apaclla.au.pe"

    async def rol_persona(db, correo):
        return "usuario" if correo == persona else None

    monkeypatch.setattr(core_auth.repo_usuarios, "rol_de", rol_persona)
    r = cliente.post("/cuentas-api", json={"email": persona})
    assert r.status_code == 201
    clave = r.json()["password"]

    token_api = cliente.post("/auth/token", json={"email": persona, "password": clave}).json()
    assert decode_token(token_api["access_token"])["origen"] == core_auth.ORIGEN_API
    assert token_api["usuario"]["rol"] == "admin"

    # Cada token resuelve el rol por su origen: la sesión de Google sigue siendo usuario.
    def rol_con(token):
        return cliente.get("/auth/yo", headers={"Authorization": f"Bearer {token}"}).json()["rol"]

    token_google = core_auth.create_token(persona, origen=core_auth.ORIGEN_GOOGLE)
    assert rol_con(token_api["access_token"]) == "admin"
    assert rol_con(token_google) == "usuario"


@pytest.mark.parametrize("dias", [0, 366])
def test_vigencia_fuera_de_rango(cliente, dias):
    r = cliente.post("/cuentas-api", json={"email": CORREO, "vigencia_dias": dias})
    assert r.status_code == 422
