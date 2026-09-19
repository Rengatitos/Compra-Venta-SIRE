"""Verificación del ID token que devuelve Google Identity Services.

El navegador hace todo el baile de OAuth con Google y entrega un ID token
firmado; aquí solo se comprueba que ese token es auténtico y de quién dice ser,
y a cambio `app.core.auth` emite el JWT propio de la aplicación. Por eso no
hace falta custodiar un `client_secret` ni registrar un `redirect_uri` por
entorno: el backend nunca habla con Google salvo para descargar sus claves
públicas.

Se verifica con PyJWT y no con `google-auth` porque PyJWT ya es dependencia (lo
es el JWT propio) y su `PyJWKClient` cachea el JWKS igual de bien; añadir
`google-auth` traería `rsa`, `pyasn1` y `cachetools` para hacer lo mismo.
"""

from __future__ import annotations

import asyncio
import logging

import jwt
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger(__name__)

# Google firma con los dos emisores, con y sin esquema, según el flujo.
EMISORES_VALIDOS = ("accounts.google.com", "https://accounts.google.com")
URL_JWKS = "https://www.googleapis.com/oauth2/v3/certs"


class ErrorIdTokenGoogle(Exception):
    """El token no es válido, no es nuestro o el correo no está verificado."""


class ErrorRedGoogle(Exception):
    """No se pudieron descargar las claves públicas de Google.

    Separado de `ErrorIdTokenGoogle` a propósito: un fallo de red no es un
    token falso, y confundirlos haría que una caída de Google se leyera en los
    logs como una oleada de intentos de acceso inválidos.
    """


_cliente: PyJWKClient | None = None


def _obtener_cliente() -> PyJWKClient:
    """Cliente JWKS perezoso y compartido.

    No se construye al importar el módulo para que los tests puedan importarlo
    sin red, y se guarda a nivel de módulo para que su caché de claves sirva de
    algo entre peticiones.
    """
    global _cliente
    if _cliente is None:
        _cliente = PyJWKClient(URL_JWKS, cache_keys=True, lifespan=3600, timeout=10)
    return _cliente


def _verificar(credential: str) -> dict:
    # Sin CLIENT_ID no se puede seguir. Esto NO puede degradarse a "valida sin
    # audiencia": `jwt.decode(audience=None)` se salta la comprobación de `aud`
    # por completo, con lo que un ID token emitido para cualquier otra
    # aplicación de Google entraría al panel sin que nada lo delate.
    if not settings.GOOGLE_CLIENT_ID:
        raise ErrorIdTokenGoogle("GOOGLE_CLIENT_ID no está configurado")

    try:
        clave = _obtener_cliente().get_signing_key_from_jwt(credential)
    except jwt.PyJWKClientError as exc:
        # PyJWKClientError no hereda de InvalidTokenError, así que si no se
        # captura aparte sale como un 500 y parece un fallo del backend.
        raise ErrorRedGoogle(str(exc)) from exc
    except jwt.InvalidTokenError as exc:
        # Este paso ya lee la cabecera del token, así que una credencial
        # malformada revienta aquí y no en el `decode` de abajo. Sin esta rama
        # salía un 500 en vez del 401 que corresponde.
        raise ErrorIdTokenGoogle(str(exc)) from exc

    try:
        datos = jwt.decode(
            credential,
            clave.key,
            # Fijo, nunca leído de la cabecera del token.
            algorithms=["RS256"],
            audience=settings.GOOGLE_CLIENT_ID,
            issuer=EMISORES_VALIDOS,
            # Margen para el desfase de reloj del contenedor.
            leeway=30,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise ErrorIdTokenGoogle(str(exc)) from exc

    # PyJWT no conoce estos dos claims. `email_verified` importa: Google lo deja
    # en False en algunas cuentas federadas de Workspace, y sin comprobarlo se
    # aceptaría un correo que su dueño nunca probó controlar.
    if datos.get("email_verified") is not True:
        raise ErrorIdTokenGoogle("El correo de esa cuenta de Google no está verificado")

    correo = (datos.get("email") or "").strip().lower()
    if not correo:
        raise ErrorIdTokenGoogle("El token de Google no trae correo")

    return {
        "email": correo,
        "nombre": datos.get("name"),
        "foto": datos.get("picture"),
    }


async def verificar_id_token(credential: str) -> dict:
    """Valida el ID token y devuelve `{email, nombre, foto}`.

    Va a un hilo porque `PyJWKClient` descarga el JWKS con `urllib` de forma
    bloqueante y la API corre con un solo worker: una llamada síncrona aquí
    congelaría todo el servicio mientras dura la descarga. Es el mismo patrón
    que `app.services.sunat.auth` usa con `requests`.
    """
    return await asyncio.to_thread(_verificar, credential)
