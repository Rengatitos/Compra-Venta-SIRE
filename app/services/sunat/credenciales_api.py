"""Credenciales de API SUNAT (client_id y clave) desde el menú SOL.

El menú SOL «Credenciales de API SUNAT › Gestión Credenciales de API SUNAT»
(`80.1.1.1.1`) abre una página que recibe un token en la URL y con él usa el
API de control de acceso:

- `GET  /v1/tecnologia/controlacceso/aplicaciones`: la aplicación del RUC (SUNAT
  admite una) con su `desClientId` y `desClientSecret`, o vacío si no tiene.
- `POST` a la misma ruta: la registra; SUNAT genera el client_id y la clave.
- `GET  /v1/tecnologia/controlacceso/apis`: el catálogo de recursos.

Aquí el navegador solo inicia sesión y abre la opción para capturar ese token;
lo demás son llamadas HTTP. Nunca se modifica una aplicación existente (la
usará quizá otro programa): si no tiene SIRE, se avisa.

Ojo: las opciones del mismo nombre que cuelgan de «Empresas» (11.5.10.1.2,
11.19.1.1.2) abren el registro antiguo, cuyas credenciales no sirven para SIRE.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx
from playwright.sync_api import sync_playwright

from app.services.scraping_sunat import _login_con_reintentos

logger = logging.getLogger(__name__)

CODIGO_OPCION = "80.1.1.1.1"
URL_APLICACIONES = "https://api.sunat.gob.pe/v1/tecnologia/controlacceso/aplicaciones"
RECURSO_SIRE = "/v1/contribuyente/migeigv"
# Alcance «solo escritorio» (servidor a servidor), el que usan las aplicaciones
# que llaman al API SIRE con usuario y clave SOL.
ALCANCE_DESKTOP = "100000"
ESPERA_TOKEN_MS = 30000


class CredencialesApiError(Exception):
    """SUNAT no dejó leer o registrar la aplicación."""


class SinRecursoSire(CredencialesApiError):
    """La empresa ya tiene una aplicación, pero sin acceso al API SIRE."""


@dataclass(frozen=True)
class AplicacionSunat:
    nombre: str
    client_id: str
    client_secret: str
    recursos: tuple[str, ...]

    @property
    def tiene_sire(self) -> bool:
        return RECURSO_SIRE in self.recursos

    def __repr__(self) -> str:  # la clave nunca a los logs
        return f"AplicacionSunat(nombre={self.nombre!r}, client_id={self.client_id[:8]!r}…)"


def _desde_api(datos) -> AplicacionSunat | None:
    if not isinstance(datos, dict):
        return None
    if not datos.get("desClientId") or not datos.get("desClientSecret"):
        return None
    recursos = tuple(
        r.get("desPathRecurso", "")
        for api in datos.get("apis") or []
        for r in api.get("recursos") or []
    )
    return AplicacionSunat(
        nombre=str(datos.get("nomApp") or ""),
        client_id=str(datos["desClientId"]),
        client_secret=str(datos["desClientSecret"]),
        recursos=recursos,
    )


def token_de_sesion(ruc: str, usuario: str, password: str, *, headless: bool = True) -> str:
    """Inicia sesión en SOL y devuelve el token de la página de credenciales.

    Bloqueante (Playwright síncrono): llamarla con `asyncio.to_thread`.
    Propaga `CredencialesSolError`/`SesionSolError` si el login SOL falla.
    """

    def log(msg: str) -> None:
        logger.info("[credenciales ruc=%s] %s", ruc, msg)

    capturados: list[str] = []

    def al_pedir(request) -> None:
        if "gestioncredenciales" in request.url:
            m = re.search(r"[?&]token=([^&#]+)", request.url)
            if m:
                capturados.append(m.group(1))

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            )
            context.on("request", al_pedir)
            page = context.new_page()
            _login_con_reintentos(page, ruc, usuario, password, log)
            page.evaluate(
                """(codigo) => {
                    if (typeof ejecuta !== 'function') throw new Error('Menú SOL no disponible');
                    ejecuta('MenuInternet.htm?action=iconExecute&code=' + codigo, false,
                            'Gestión Credenciales de API SUNAT', '#nivel1_80', codigo);
                }""",
                CODIGO_OPCION,
            )
            for _ in range(ESPERA_TOKEN_MS // 250):
                if capturados:
                    return capturados[0]
                page.wait_for_timeout(250)
        finally:
            browser.close()
    raise CredencialesApiError("SOL no abrió «Gestión Credenciales de API SUNAT»")


def _llamar(metodo: str, token: str, cuerpo: dict | None = None):
    try:
        r = httpx.request(
            metodo,
            URL_APLICACIONES,
            json=cuerpo,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        motivo = type(exc).__name__
        raise CredencialesApiError(f"Sin conexión con el API de SUNAT: {motivo}") from None
    if r.status_code >= 400:
        try:
            detalle = r.json().get("msg") or r.json().get("message") or ""
        except ValueError:
            detalle = ""
        raise CredencialesApiError(f"SUNAT respondió {r.status_code} {detalle}".strip())
    if not r.text.strip():
        return None
    try:
        return r.json()
    except ValueError:
        return None


def leer(token: str) -> AplicacionSunat | None:
    return _desde_api(_llamar("GET", token))


def registrar(token: str, nombre: str, url: str) -> AplicacionSunat:
    """Registra la aplicación con acceso a SIRE y la devuelve ya con su clave."""
    _llamar("POST", token, {
        "id": None,
        "expFlujoAutoriz": ALCANCE_DESKTOP,
        "nomApp": nombre,
        "desUrlApp": url,
        "recursos": [{"desPathRecurso": RECURSO_SIRE}],
    })
    app = leer(token)
    if app is None:
        raise CredencialesApiError("SUNAT aceptó el registro pero no devolvió la aplicación")
    return app


def obtener(
    ruc: str, usuario: str, password: str, *, crear_con: tuple[str, str] | None
) -> tuple[AplicacionSunat, bool]:
    """La aplicación de la empresa y si se acaba de crear. Bloqueante.

    Con `crear_con=(nombre, url)` la registra si la empresa no tiene ninguna.
    """
    token = token_de_sesion(ruc, usuario, password)
    app = leer(token)
    if app is not None:
        if not app.tiene_sire:
            raise SinRecursoSire(
                f"La aplicación «{app.nombre}» de SUNAT no tiene acceso a SIRE (MIGE RCE y RVIE). "
                "Agrégaselo en SOL › Credenciales de API SUNAT."
            )
        return app, False
    if crear_con is None:
        raise CredencialesApiError("La empresa no tiene una aplicación registrada en SUNAT")
    nombre, url = crear_con
    logger.info("[credenciales ruc=%s] Registrando la aplicación %r en SUNAT", ruc, nombre)
    return registrar(token, nombre, url), True
