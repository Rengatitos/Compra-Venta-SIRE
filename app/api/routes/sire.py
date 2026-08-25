import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import verify_user
from app.db.database import get_db, get_user_db
from app.services import sire_service
from app.schemas.generic import SireResponse


limiter = Limiter(key_func=get_remote_address)
router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=SireResponse)
@limiter.limit("10/minute")
async def get_sire_propuesta(
    request: Request,
    tenant_id: str,
    cliente_id: str,
    cuenta_id: str,
    periodo: str,
    db=Depends(get_db),
    user_db=Depends(get_user_db),
    user=Depends(verify_user),
):
    try:
        logger.info(
            "GET propuesta SIRE user_id=%s periodo=%s tenant_id=%s cliente_id=%s cuenta_id=%s",
            user.get("_id"),
            periodo,
            tenant_id,
            cliente_id,
            cuenta_id,
        )
        resultado = await sire_service.obtener_propuesta(
            tenant_id,
            cliente_id,
            cuenta_id,
            periodo,
            db,
            user_db,
        )
        return {
            "estado": "exito",
            "facturas_guardadas": len(resultado),
            "mensaje": (
                f"Se guardaron {len(resultado)} facturas."
                if resultado
                else "No se encontraron propuestas para el periodo indicado."
            ),
        }
    except Exception as e:
        logger.exception(
            "Error en propuesta SIRE periodo=%s tenant_id=%s cliente_id=%s cuenta_id=%s",
            periodo,
            tenant_id,
            cliente_id,
            cuenta_id,
        )
        raise HTTPException(status_code=500, detail=str(e))


async def _run_scrape_background(tenant_id, cliente_id, cuenta_id, periodo, db, user_db, user_id):
    try:
        logger.info("BG scrape_detalles iniciado user_id=%s periodo=%s", user_id, periodo)
        resultado = await sire_service.procesar_detalles_scraper(
            tenant_id,
            cliente_id,
            cuenta_id,
            periodo,
            db,
            user_db,
            debug=False,
            headed=False,
        )
        logger.info(
            "BG scrape_detalles finalizado user_id=%s periodo=%s procesadas=%s con_detalle=%s",
            user_id,
            periodo,
            resultado.get("facturas_procesadas", 0),
            resultado.get("facturas_con_detalles_encontrados", 0),
        )
    except Exception:
        logger.exception("BG scrape_detalles error user_id=%s periodo=%s", user_id, periodo)


@router.post("/scrape-detalles")
@limiter.limit("5/minute")
async def post_scrape_detalles(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str,
    cliente_id: str,
    cuenta_id: str,
    periodo: str,
    db=Depends(get_db),
    user_db=Depends(get_user_db),
    user=Depends(verify_user),
):
    user_id = str(user.get("_id"))
    logger.info("POST scrape_detalles_sire user_id=%s periodo=%s (background)", user_id, periodo)
    background_tasks.add_task(
        _run_scrape_background,
        tenant_id, cliente_id, cuenta_id, periodo, db, user_db, user_id,
    )
    return {
        "estado": "iniciado",
        "mensaje": "Extracción de detalles SUNAT iniciada en segundo plano. Los datos estarán disponibles en unos minutos.",
        "facturas_procesadas": 0,
        "facturas_con_detalles_encontrados": 0,
    }
