"""Obtiene el client_id y la clave del API SUNAT de una empresa sin teclearlos.

Con el RUC, el usuario y la clave SOL entra al menú SOL (ver
`app.services.sunat.credenciales_api`), toma la aplicación que la empresa ya
tenga registrada o, si no tiene, registra una con acceso a SIRE. Luego pide un
token del API SIRE con ella para confirmar que funciona.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.core.encryption import decrypt_password
from app.repositories import empresas as repo_empresas
from app.services.sunat import credenciales_api
from app.services.sunat.auth import obtener_token

logger = logging.getLogger(__name__)

# Un navegador a la vez: en la VM de 4 GB dos Chromium más la API no caben.
_candado = asyncio.Lock()

MENSAJES = {
    (False, True): "Se usó la aplicación que la empresa ya tenía en SUNAT.",
    (True, True): "Se registró una aplicación nueva en SUNAT y ya funciona.",
    (True, False): (
        "Se registró una aplicación nueva en SUNAT. SUNAT puede tardar unos minutos en "
        "activarla: si una descarga falla, vuelve a intentarlo en un rato."
    ),
    (False, False): (
        "Se tomaron las credenciales de SUNAT, pero SUNAT no entregó un token SIRE con ellas. "
        "Revisa la aplicación en SOL › Credenciales de API SUNAT."
    ),
}


async def obtener(db, empresa: dict[str, Any], *, crear: bool = True) -> dict[str, Any]:
    """Busca (o registra) las credenciales y las guarda en la empresa.

    Devuelve un resumen sin la clave. Propaga `CredencialesSolError` (usuario o
    clave SOL mal), `SesionSolError` y `CredencialesApiError`.
    """
    ruc, usuario = empresa["ruc"], empresa["usuario"]
    password = decrypt_password(empresa["password"])
    crear_con = (settings.SUNAT_APP_NOMBRE, settings.SUNAT_APP_URL) if crear else None

    async with _candado:
        app, creada = await asyncio.to_thread(
            credenciales_api.obtener, ruc, usuario, password, crear_con=crear_con
        )

    token, error = await obtener_token(ruc, usuario, password, app.client_id, app.client_secret)
    if not token:
        logger.warning("Credenciales SUNAT de ruc=%s sin token SIRE: %s", ruc, (error or "")[:160])

    await repo_empresas.actualizar(db, empresa["_id"], {
        "sunat_client_id": app.client_id,
        "sunat_client_secret": app.client_secret,
        "sunat_token": token,
    })
    logger.info("Credenciales SUNAT guardadas ruc=%s app=%r creada=%s", ruc, app.nombre, creada)
    return {
        "origen": "creada" if creada else "existente",
        "aplicacion": app.nombre,
        # Solo un trozo: la clave no sale nunca y el id completo no hace falta.
        "client_id": app.client_id[:8] + "…",
        "token_valido": bool(token),
        "mensaje": MENSAJES[(creada, bool(token))],
    }
