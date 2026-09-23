import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import usuario_actual
from app.db.database import get_db
from app.domain import ciiu
from app.services import ficha_ruc_service
from app.services.sunat.ficha_ruc import FichaNoEncontrada, FichaRuc, es_ruc

router = APIRouter(dependencies=[Depends(usuario_actual)])
# Catálogo CIIU para elegir las actividades de una empresa en Ajustes.
router_ciiu = APIRouter(dependencies=[Depends(usuario_actual)])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router_ciiu.get("", summary="Buscar actividades en el catálogo CIIU Rev. 4")
async def buscar_ciiu(q: str = Query(..., min_length=2, description="Código o palabras")):
    return ciiu.buscar(q)


@router.get(
    "/{ruc}",
    response_model=FichaRuc,
    summary="Ficha RUC de cualquier contribuyente (actividades CIIU, comprobantes)",
)
@limiter.limit("20/minute")
async def consultar_ruc(
    request: Request,
    ruc: str = Path(..., description="RUC de 11 dígitos"),
    refrescar: bool = Query(False, description="Ignora la caché y consulta SUNAT"),
    db=Depends(get_db),
):
    """Sirve para proveedores y clientes, estén o no registrados. La respuesta
    queda en caché (`FICHA_RUC_VIGENCIA_DIAS`) y la reutiliza el clasificador."""
    if not es_ruc(ruc):
        raise HTTPException(status_code=422, detail="El RUC debe tener 11 dígitos")
    try:
        return await ficha_ruc_service.obtener(db, ruc, refrescar=refrescar)
    except FichaNoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Consulta RUC fallida ruc=%s", ruc)
        raise HTTPException(
            status_code=502, detail=f"No se pudo consultar la ficha RUC en SUNAT: {exc}"
        ) from exc
