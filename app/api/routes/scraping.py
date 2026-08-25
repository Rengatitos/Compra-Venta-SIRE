from fastapi import APIRouter, HTTPException, Depends, Request, Query
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.services import scraping_sunat
from app.db.database import get_db, get_user_db
from app.core.auth import verify_user
from app.schemas.generic import ScrapingResponse

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/", response_model=ScrapingResponse)
@limiter.limit("5/minute")
async def ejecutar_scraping(
    request: Request,
    tenant_id: str,
    cliente_id: str,
    cuenta_id: str,
    periodo: str,
    debug: bool = Query(False, description="Activa logs y artefactos de depuracion"),
    headed: bool = Query(False, description="Abre navegador visible (requiere entorno con UI)"),
    slow_mo_ms: int = Query(0, ge=0, le=3000, description="Pausa entre acciones de Playwright en milisegundos"),
    db=Depends(get_db),
    user_db=Depends(get_user_db),
    user=Depends(verify_user),
):
    """
    Ejecuta el scraping Playwright para renovar sunat_client_id y sunat_client_secret
    y guardarlos en la BD del usuario.

    """
    try:
        resultado = await scraping_sunat.login_y_consultar(
            tenant_id,
            cliente_id,
            cuenta_id,
            periodo,
            db,
            user_db,
            debug=debug,
            headed=headed,
            slow_mo_ms=slow_mo_ms,
        )
        return {"estado": "éxito", **resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
