"""Configuración del correo desde el panel: plantilla, contraseña y permisos."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1.routes import solicitudes as ruta
from app.core.auth import exigir_admin, usuario_actual
from app.core.encryption import decrypt_password
from app.db.database import get_db
from app.domain.configuracion_correo import (
    CUERPO_POR_DEFECTO,
    ConfiguracionCorreo,
    Valor,
    desde_documento,
    renderizar_html,
    renderizar_texto,
)

ADMIN = {"email": "admin@example.com", "rol": "admin"}


# --- Plantilla --------------------------------------------------------------


def test_sustituye_las_variables_y_deja_a_la_vista_las_desconocidas():
    valores = {"empresas": Valor("Alfa, Beta")}
    assert renderizar_texto("Listo: {{empresas}} {{ empresas }} {{otra}}", valores) == (
        "Listo: Alfa, Beta Alfa, Beta {{otra}}"
    )


def test_el_html_escapa_la_plantilla_pero_no_el_html_de_las_variables():
    valores = {"resultados": Valor("- Alfa", "<table><tr><td>Alfa</td></tr></table>")}
    html = renderizar_html("<script>x</script>\n{{resultados}}", valores)
    assert html == "&lt;script&gt;x&lt;/script&gt;<br>\n<table><tr><td>Alfa</td></tr></table>"


def test_sin_documento_se_usan_los_valores_por_defecto():
    config = desde_documento(None)
    assert config.plantilla_cuerpo == CUERPO_POR_DEFECTO
    assert (config.host, config.usuario) == ("smtp.gmail.com", "sistemaapacllasire@gmail.com")
    # Un servidor guardado en blanco no tapa la cuenta del sistema.
    assert desde_documento({"host": "", "usuario": ""}).usuario == "sistemaapacllasire@gmail.com"
    assert config.permitido("cualquiera@x.pe")
    assert desde_documento({"host": "smtp.x.pe", "puerto": None}).puerto == 587


def test_el_remitente_lleva_nombre_y_cae_al_usuario():
    assert ConfiguracionCorreo(usuario="u@x.pe").remitente == "Sire Apaclla <u@x.pe>"
    assert ConfiguracionCorreo(remitente_nombre="", remitente_correo="r@x.pe").remitente == "r@x.pe"


# --- Rutas ------------------------------------------------------------------


class Guardada:
    def __init__(self) -> None:
        self.config = ConfiguracionCorreo()
        self.por: str | None = None

    async def obtener(self, db):
        return self.config

    async def guardar(self, db, cambios, *, por):
        self.config = replace(self.config, **cambios)
        self.por = por
        return self.config


@pytest.fixture
def guardada(monkeypatch):
    g = Guardada()
    monkeypatch.setattr(ruta.repo_configuracion, "obtener_correo", g.obtener)
    monkeypatch.setattr(ruta.repo_configuracion, "guardar_correo", g.guardar)
    monkeypatch.setattr(ruta.correo_service.repo_configuracion, "obtener_correo", g.obtener)
    return g


def cliente_con(usuario):
    ruta.limiter.reset()
    app = FastAPI()
    app.state.limiter = ruta.limiter
    app.include_router(ruta.router_correos, prefix="/correos")
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[usuario_actual] = lambda: usuario

    def solo_admin():
        if usuario["rol"] != "admin":
            raise HTTPException(status_code=403, detail="Solo administradores")
        return usuario

    app.dependency_overrides[exigir_admin] = solo_admin
    return TestClient(app)


def test_guardar_cifra_la_contrasena_y_no_la_devuelve_nunca(guardada):
    cliente = cliente_con(ADMIN)

    r = cliente.put("/correos/configuracion", json={
        "host": " smtp.gmail.com ", "usuario": "sire@gmail.com", "password": "clave-app",
        "destinatarios_permitidos": ["Prueba@Gmail.com", "prueba@gmail.com"],
    })

    assert r.status_code == 200
    cuerpo = r.json()
    assert "clave-app" not in r.text
    assert "password_cifrada" not in cuerpo
    assert cuerpo["password_configurada"] is True
    assert cuerpo["host"] == "smtp.gmail.com"
    assert cuerpo["destinatarios_permitidos"] == ["prueba@gmail.com"]
    assert decrypt_password(guardada.config.password_cifrada) == "clave-app"
    assert guardada.por == ADMIN["email"]
    assert {v["nombre"] for v in cuerpo["variables"]} >= {"empresas", "resultados", "entrega"}


def test_sin_contrasena_se_conserva_la_guardada(guardada):
    cliente = cliente_con(ADMIN)
    cliente.put("/correos/configuracion", json={"host": "smtp.x.pe", "password": "primera"})
    cifrada = guardada.config.password_cifrada

    cliente.put("/correos/configuracion", json={"puerto": 465, "password": ""})

    assert guardada.config.password_cifrada == cifrada
    assert guardada.config.puerto == 465


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"puerto": 0},
        {"seguridad": "tls"},
        {"remitente_correo": "no-es-correo"},
        {"url_publica": "sire.x.pe"},
        {"plantilla_asunto": ""},
    ],
)
def test_rechaza_valores_invalidos(guardada, cuerpo):
    assert cliente_con(ADMIN).put("/correos/configuracion", json=cuerpo).status_code == 422


def test_la_vista_previa_no_guarda_nada(guardada):
    r = cliente_con(ADMIN).post("/correos/configuracion/vista-previa", json={
        "plantilla_asunto": "Hecho: {{resumen}}",
        "plantilla_cuerpo": "Para {{destinatario}}\n{{resultados}}",
    })
    assert r.status_code == 200
    assert r.json()["asunto"] == "Hecho: 2 empresas, 2 periodos"
    assert "<table" in r.json()["html"]
    assert guardada.config.plantilla_asunto != "Hecho: {{resumen}}"


def test_la_prueba_explica_por_que_no_salio(guardada, monkeypatch):
    monkeypatch.setattr(ruta.correo_service.settings, "CORREO_SMTP_PASSWORD", None)
    r = cliente_con(ADMIN).post("/correos/configuracion/prueba", json={"destinatario": "a@b.pe"})
    assert r.status_code == 422
    assert "contraseña de aplicación" in r.json()["detail"]


def test_solo_un_administrador_ve_o_cambia_la_configuracion(guardada):
    cliente = cliente_con({"email": "user@example.com", "rol": "usuario"})
    assert cliente.get("/correos/configuracion").status_code == 403
    assert cliente.put("/correos/configuracion", json={"host": "x"}).status_code == 403
