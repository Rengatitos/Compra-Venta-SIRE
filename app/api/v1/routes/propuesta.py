import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual, libro_valido, periodo_valido
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.schemas.generic import StatusResponse
from app.services import propuesta_service
from app.services.sunat.auth import ErrorSunat

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/libros/{libro}/propuesta",
    response_model=StatusResponse,
    summary="Sincronizar la propuesta del SIRE para el periodo",
)
@limiter.limit("10/minute")
async def sincronizar_propuesta(
    request: Request,
    periodo: str = Depends(periodo_valido),
    libro: Libro = Depends(libro_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    logger.info(
        "Sincronizando propuesta ruc=%s periodo=%s libro=%s",
        empresa.get("ruc"),
        periodo,
        libro.value,
    )

    try:
        resultado = await propuesta_service.sincronizar(db, empresa, periodo, libro)
    except ErrorSunat as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "estado": "exito",
        "mensaje": resultado.pop("mensaje"),
        "datos": resultado,
    }
