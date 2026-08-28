from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import requests
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.encryption import decrypt_password
from app.repositories import empresas as repo_empresas

logger = logging.getLogger(__name__)

URL_TOKEN = "https://api-seguridad.sunat.gob.pe/v1/clientessol/{client_id}/oauth2/token/"
SCOPE_SIRE = "https://api-sire.sunat.gob.pe"


class ErrorSunat(Exception):
    pass


def credenciales_cliente(empresa: dict[str, Any]) -> tuple[str, str]:
    client_id = empresa.get("sunat_client_id") or (settings.SUNAT_CLIENT_ID or "").strip()
    client_secret = empresa.get("sunat_client_secret") or (
        settings.SUNAT_CLIENT_SECRET or ""
    ).strip()
    return client_id, client_secret


async def obtener_token(
    ruc: str, usuario: str, password: str, client_id: str, client_secret: str
) -> tuple[str | None, str | None]:
    url = URL_TOKEN.format(client_id=client_id)
    payload = {
        "grant_type": "password",
        "scope": SCOPE_SIRE,
        "client_id": client_id,
        "client_secret": client_secret,
        "username": f"{ruc}{usuario}",
        "password": password,
    }

    try:
        respuesta = await asyncio.to_thread(
            requests.post,
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.exception("Error de conexión obteniendo token SUNAT ruc=%s", ruc)
        return None, f"Error de conexión con la API de SUNAT: {exc}"

    if respuesta.status_code == 200:
        return respuesta.json().get("access_token"), None
    return None, f"Error de la API SUNAT ({respuesta.status_code}): {respuesta.text[:500]}"


async def renovar_token(
    db: AsyncIOMotorDatabase, empresa: dict[str, Any]
) -> tuple[str | None, str | None]:
    client_id, client_secret = credenciales_cliente(empresa)
    if not client_id or not client_secret:
        return None, "La empresa no tiene sunat_client_id/sunat_client_secret configurados"

    try:
        password = decrypt_password(empresa["password"]) if empresa.get("password") else ""
    except Exception:
        logger.exception("No se pudo descifrar la contraseña SOL ruc=%s", empresa.get("ruc"))
        return None, "No se pudo descifrar la contraseña SOL almacenada"

    token, error = await obtener_token(
        empresa["ruc"], empresa["usuario"], password, client_id, client_secret
    )
    if token:
        await repo_empresas.guardar_token_sunat(db, empresa["_id"], token)
        empresa["sunat_token"] = token
    return token, error


async def peticion_autenticada(
    db: AsyncIOMotorDatabase,
    empresa: dict[str, Any],
    hacer_peticion: Callable[[str], requests.Response],
) -> requests.Response:
    token = empresa.get("sunat_token")
    if not token:
        token, error = await renovar_token(db, empresa)
        if not token:
            raise ErrorSunat(f"No se pudo obtener el token de SUNAT: {error}")

    respuesta = await asyncio.to_thread(hacer_peticion, token)
    if respuesta.status_code != 401:
        return respuesta

    logger.info("Token SUNAT expirado ruc=%s, renovando", empresa.get("ruc"))
    token, error = await renovar_token(db, empresa)
    if not token:
        raise ErrorSunat(f"El token expiró y falló la renovación: {error}")

    return await asyncio.to_thread(hacer_peticion, token)
