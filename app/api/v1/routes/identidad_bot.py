"""Identificación de la empresa para el canal de WhatsApp de sire-bot.

En WhatsApp no hay panel desde donde generar un código de vinculación: el chat
se vincula con el RUC y el usuario SOL de la empresa. Ambas rutas son solo del
bot (`X-Api-Key`) y nunca devuelven el usuario SOL, solo dicen si coincide.
"""

import asyncio
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_para_bot
from app.db.database import get_db
from app.schemas.comprobante_externo import CanjeResponse
from app.services import ficha_ruc_service

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

# Si la razón social no está guardada se consulta la ficha RUC en SUNAT; el bot
# está esperando para responder al chat, así que no se le espera más que esto.
ESPERA_FICHA_S = 25


class IdentidadEmpresa(BaseModel):
    ruc: str
    razon_social: str | None = None


class VerificarUsuario(BaseModel):
    usuario: str = Field(..., min_length=1, max_length=40)


def _por_ruc(request: Request) -> str:
    # Todo el tráfico del bot sale de la misma IP: el límite se cuenta por
    # empresa para acotar que alguien pruebe usuarios SOL a ciegas.
    return f"{get_remote_address(request)}:{request.path_params.get('ruc', '')}"


def _normalizar(usuario: str) -> str:
    return usuario.strip().upper()


async def _razon_social(db, empresa: dict) -> str | None:
    guardada = (empresa.get("ficha_ruc") or {}).get("razon_social") or empresa.get("nombre")
    if guardada and guardada.strip():
        return guardada.strip()
    try:
        ficha = await asyncio.wait_for(
            ficha_ruc_service.obtener(db, empresa["ruc"]), timeout=ESPERA_FICHA_S
        )
    except Exception as exc:  # noqa: BLE001 - sin nombre el bot sigue igual
        logger.warning(
            "Sin razón social para ruc=%s: %s", empresa["ruc"], type(exc).__name__
        )
        return None
    return ficha.razon_social.strip() or None


@router.get(
    "/identidad",
    response_model=IdentidadEmpresa,
    summary="RUC registrado y su razón social (solo sire-bot, X-Api-Key)",
)
@limiter.limit("30/minute")
async def identidad(
    request: Request,
    empresa: dict = Depends(empresa_para_bot),
    db=Depends(get_db),
):
    return {"ruc": empresa["ruc"], "razon_social": await _razon_social(db, empresa)}


@router.post(
    "/verificar-usuario",
    response_model=CanjeResponse,
    summary="Comprobar el usuario SOL de la empresa (solo sire-bot, X-Api-Key)",
    responses={400: {"description": "El usuario no corresponde a ese RUC"}},
)
@limiter.limit("10/minute", key_func=_por_ruc)
async def verificar_usuario(
    request: Request,
    datos: VerificarUsuario,
    empresa: dict = Depends(empresa_para_bot),
    db=Depends(get_db),
):
    esperado = _normalizar(empresa.get("usuario") or "")
    recibido = _normalizar(datos.usuario)
    if not esperado or not hmac.compare_digest(recibido.encode(), esperado.encode()):
        logger.info("Usuario SOL incorrecto desde el bot ruc=%s", empresa["ruc"])
        raise HTTPException(status_code=400, detail="El usuario no corresponde a ese RUC")

    nombre = await _razon_social(db, empresa) or f"RUC {empresa['ruc']}"
    logger.info("Chat de WhatsApp vinculado con usuario SOL ruc=%s", empresa["ruc"])
    return {"empresa": {"ruc": empresa["ruc"], "nombre": nombre}}
