"""Autenticación de servicio para sire-bot (Apaclla Bot).

El bot no usa el JWT del panel: no es una persona y no pasa por la allowlist de
Google. Se identifica con una clave compartida en `X-Api-Key`, comparada en
tiempo constante contra `SIRE_BOT_API_KEY`.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings

CABECERA = "X-Api-Key"


def clave_valida(recibida: str | None) -> bool:
    esperada = settings.SIRE_BOT_API_KEY
    if not esperada or not recibida:
        return False
    return hmac.compare_digest(recibida.encode(), esperada.encode())


async def bot_autorizado(x_api_key: str | None = Header(None, alias=CABECERA)) -> None:
    """Deja pasar solo al bot. Falla cerrado si la integración no está configurada."""
    if not settings.SIRE_BOT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La integración con el bot no está configurada",
        )
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Falta la cabecera {CABECERA}",
        )
    if not clave_valida(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{CABECERA} inválida",
        )
