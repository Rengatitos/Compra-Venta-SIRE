import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual, empresa_para_bot
from app.core.auth import usuario_actual
from app.db.database import get_db
from app.schemas.comprobante_externo import (
    CanjeRequest,
    CanjeResponse,
    CodigoVinculacionResponse,
)
from app.services import vinculacion_service
from app.services.vinculacion_service import CodigoInvalido, CodigoYaUsado

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


def _ip_y_ruc(request: Request) -> str:
    # Todo el tráfico del bot sale de la misma IP, así que por sí sola no frena
    # a nadie: el límite de canje se cuenta por empresa para acotar la fuerza
    # bruta sobre un código de 6 dígitos.
    return f"{get_remote_address(request)}:{request.path_params.get('ruc', '')}"


@router.post(
    "",
    status_code=201,
    response_model=CodigoVinculacionResponse,
    summary="Generar un código para vincular Apaclla Bot con la empresa",
)
@limiter.limit("10/minute")
async def generar_codigo(
    request: Request,
    empresa: dict = Depends(empresa_actual),
    usuario: dict = Depends(usuario_actual),
    db=Depends(get_db),
):
    resultado = await vinculacion_service.generar(db, empresa, usuario["email"])
    logger.info("Código de vinculación generado ruc=%s por=%s", empresa["ruc"], usuario["email"])
    return resultado


@router.post(
    "/canjear",
    response_model=CanjeResponse,
    summary="Canjear un código de vinculación (solo sire-bot, X-Api-Key)",
)
@limiter.limit("10/minute", key_func=_ip_y_ruc)
async def canjear_codigo(
    request: Request,
    datos: CanjeRequest,
    empresa: dict = Depends(empresa_para_bot),
    db=Depends(get_db),
):
    try:
        resultado = await vinculacion_service.canjear(
            db, empresa, datos.codigo, datos.dispositivo_id
        )
    except CodigoYaUsado:
        raise HTTPException(
            status_code=409, detail="El código de vinculación ya fue canjeado"
        ) from None
    except CodigoInvalido:
        raise HTTPException(status_code=400, detail="Código inválido o expirado") from None

    logger.info("Dispositivo vinculado ruc=%s dispositivo=%s", empresa["ruc"], datos.dispositivo_id)
    return resultado
