import asyncio

from fastapi import APIRouter, Depends, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth import decode_token
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.services import analytics_service

router = APIRouter()
security = HTTPBearer()


async def token_dashboard(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    return decode_token(credentials.credentials)


@router.get("/summary", summary="Totales del periodo")
async def summary(
    periodo: str,
    rucs: str | None = None,
    libro: Libro = Query(Libro.COMPRAS),
    db=Depends(get_db),
    _: dict = Depends(token_dashboard),
):
    ids = await analytics_service.get_target_empresa_ids(rucs, db)
    return await analytics_service.get_summary(ids, periodo, libro, db)


@router.get("/top-contrapartes", summary="Contrapartes con mayor monto")
async def top_contrapartes(
    periodo: str,
    rucs: str | None = None,
    limit: int = 5,
    libro: Libro = Query(Libro.COMPRAS),
    db=Depends(get_db),
    _: dict = Depends(token_dashboard),
):
    ids = await analytics_service.get_target_empresa_ids(rucs, db)
    return await analytics_service.get_top_contrapartes(ids, periodo, limit, libro, db)


@router.get("/ai-classification", summary="Distribución de la clasificación por IA")
async def ai_classification(
    periodo: str,
    rucs: str | None = None,
    libro: Libro = Query(Libro.COMPRAS),
    db=Depends(get_db),
    _: dict = Depends(token_dashboard),
):
    ids = await analytics_service.get_target_empresa_ids(rucs, db)
    return await analytics_service.get_ai_classification(ids, periodo, libro, db)


@router.get("/comprobantes-por-dia", summary="Comprobantes agrupados por día")
async def comprobantes_por_dia(
    periodo: str,
    rucs: str | None = None,
    libro: Libro = Query(Libro.COMPRAS),
    db=Depends(get_db),
    _: dict = Depends(token_dashboard),
):
    ids = await analytics_service.get_target_empresa_ids(rucs, db)
    return await analytics_service.get_comprobantes_by_day(ids, periodo, libro, db)


@router.get("/periodos", summary="Periodos con datos")
async def periodos_disponibles(
    rucs: str | None = None,
    db=Depends(get_db),
    _: dict = Depends(token_dashboard),
):
    ids = await analytics_service.get_target_empresa_ids(rucs, db)
    return await analytics_service.periodos_disponibles(ids, db)


@router.get("/dashboard-data", summary="Todo el dashboard en una sola llamada")
async def dashboard_data(
    periodo: str,
    rucs: str | None = None,
    libro: Libro = Query(Libro.COMPRAS),
    db=Depends(get_db),
    _: dict = Depends(token_dashboard),
):
    ids = await analytics_service.get_target_empresa_ids(rucs, db)

    resumen, contrapartes, clasificacion, por_dia, listado = await asyncio.gather(
        analytics_service.get_summary(ids, periodo, libro, db),
        analytics_service.get_top_contrapartes(ids, periodo, 5, libro, db),
        analytics_service.get_ai_classification(ids, periodo, libro, db),
        analytics_service.get_comprobantes_by_day(ids, periodo, libro, db),
        analytics_service.get_comprobantes_list(ids, periodo, libro, db),
    )

    return {
        "summary": resumen,
        "top_contrapartes": contrapartes,
        "ai_classification": clasificacion,
        "comprobantes_por_dia": por_dia,
        "comprobantes": listado,
    }
