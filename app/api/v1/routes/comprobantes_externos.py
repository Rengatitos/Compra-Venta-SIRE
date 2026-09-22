import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual, empresa_para_bot, empresa_para_usuario_o_bot
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.domain.comprobante_externo import Fuente
from app.domain.periodo import MENSAJE_FORMATO, es_valido
from app.schemas.comprobante_externo import (
    ComprobanteExternoCreate,
    ComprobanteExternoRecibido,
    ComprobanteExternoResponse,
    ListaComprobantesExternos,
)
from app.services import comprobantes_externos_service as servicio
from app.services.imagenes_externas import ImagenInvalida

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

NO_ENCONTRADO = "No se encontró ese comprobante externo"


@router.post(
    "",
    status_code=201,
    response_model=ComprobanteExternoRecibido,
    summary="Recibir un comprobante desde sire-bot (X-Api-Key)",
    responses={
        200: {"description": "Reintento: el id_externo ya estaba registrado"},
        409: {"description": "Otro envío ya registró este mismo comprobante"},
    },
)
@limiter.limit("120/minute")
async def recibir(
    request: Request,
    response: Response,
    datos: ComprobanteExternoCreate,
    empresa: dict = Depends(empresa_para_bot),
    db=Depends(get_db),
):
    try:
        cuerpo, creado = await servicio.recibir(db, empresa, datos)
    except ImagenInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except servicio.Duplicado as exc:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Este comprobante ya se registró desde el bot con otro envío",
                "comprobante_externo_id": exc.existente_id,
            },
        )

    if creado:
        logger.info(
            "Comprobante externo recibido ruc=%s id=%s fuente=%s",
            empresa["ruc"],
            cuerpo["id"],
            datos.fuente.value,
        )
    else:
        response.status_code = 200
    return cuerpo


@router.get(
    "",
    response_model=ListaComprobantesExternos,
    summary="Listar los comprobantes recibidos desde el bot",
)
async def listar(
    libro: Libro | None = Query(None),
    periodo: str | None = Query(None, description="YYYYMM"),
    fuente: Fuente | None = Query(None),
    limit: int = Query(100, ge=1, le=100),
    skip: int = Query(0, ge=0),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    if periodo is not None and not es_valido(periodo):
        raise HTTPException(status_code=422, detail=MENSAJE_FORMATO)
    return await servicio.listar(
        db,
        empresa,
        libro=libro.value if libro else None,
        periodo=periodo,
        fuente=fuente.value if fuente else None,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{id_}",
    response_model=ComprobanteExternoResponse,
    summary="Detalle de un comprobante externo (panel o sire-bot)",
)
async def obtener(
    id_: str,
    empresa: dict = Depends(empresa_para_usuario_o_bot),
    db=Depends(get_db),
):
    detalle = await servicio.obtener(db, empresa, id_)
    if not detalle:
        raise HTTPException(status_code=404, detail=NO_ENCONTRADO)
    return detalle


@router.get("/{id_}/imagen", summary="Foto del comprobante externo")
async def imagen(
    id_: str,
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    resultado = await servicio.imagen(db, empresa, id_)
    if not resultado:
        raise HTTPException(status_code=404, detail="Este comprobante no tiene foto disponible")
    contenido, mime = resultado
    return Response(
        content=contenido, media_type=mime, headers={"Cache-Control": "private, max-age=3600"}
    )
