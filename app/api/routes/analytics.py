import asyncio
from fastapi import APIRouter, HTTPException, Depends, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
import jwt

from app.core.auth import decode_token
from app.db.database import get_db
from app.services import analytics_service
from shared_auth_lib.auth_utils import JWT_SECRET_KEY, JWT_ALGORITHM, INTERNAL_APIS_AUDIENCE, AUTH_API_ISSUER

security = HTTPBearer()

router = APIRouter()


async def verify_dashboard_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    token = credentials.credentials
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], audience=INTERNAL_APIS_AUDIENCE, issuer=AUTH_API_ISSUER)
    except Exception:
        pass
    try:
        return decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")


@router.get("/summary")
async def get_summary(
    periodo: str,
    rucs: Optional[str] = None,
    tipo_operacion: str = Query("compras"),
    db=Depends(get_db),
    token_payload: dict = Depends(verify_dashboard_token)
):
    target_ids = await analytics_service.get_target_user_ids(rucs, db, token_payload)
    return await analytics_service.get_summary(target_ids, periodo, tipo_operacion, db)

@router.get("/top-suppliers")
async def get_top_suppliers(
    periodo: str,
    rucs: Optional[str] = None,
    limit: int = 5,
    tipo_operacion: str = Query("compras"),
    db=Depends(get_db),
    token_payload: dict = Depends(verify_dashboard_token)
):
    target_ids = await analytics_service.get_target_user_ids(rucs, db, token_payload)
    return await analytics_service.get_top_suppliers(target_ids, periodo, limit, tipo_operacion, db)

@router.get("/ai-classification")
async def get_ai_classification(
    periodo: str,
    rucs: Optional[str] = None,
    tipo_operacion: str = Query("compras"),
    db=Depends(get_db),
    token_payload: dict = Depends(verify_dashboard_token)
):
    target_ids = await analytics_service.get_target_user_ids(rucs, db, token_payload)
    return await analytics_service.get_ai_classification(target_ids, periodo, tipo_operacion, db)

@router.get("/invoices-by-day")
async def get_invoices_by_day(
    periodo: str,
    rucs: Optional[str] = None,
    tipo_operacion: str = Query("compras"),
    db=Depends(get_db),
    token_payload: dict = Depends(verify_dashboard_token)
):
    target_ids = await analytics_service.get_target_user_ids(rucs, db, token_payload)
    return await analytics_service.get_invoices_by_day(target_ids, periodo, tipo_operacion, db)

@router.get("/periodos")
async def get_available_periodos(
    rucs: Optional[str] = None,
    db=Depends(get_db),
    token_payload: dict = Depends(verify_dashboard_token)
):
    target_ids = await analytics_service.get_target_user_ids(rucs, db, token_payload)
    if not target_ids:
        return []
    facturas_col = db["facturas"]
    periodos = await facturas_col.distinct("periodo", {"user_id": {"$in": target_ids}})
    return sorted(periodos, reverse=True)


@router.get("/dashboard-data")
async def get_dashboard_data(
    periodo: str,
    rucs: Optional[str] = None,
    tipo_operacion: str = Query("compras"),
    db=Depends(get_db),
    token_payload: dict = Depends(verify_dashboard_token)
):
    target_ids = await analytics_service.get_target_user_ids(rucs, db, token_payload)

    summary, top_suppliers, ai_classification, invoices_by_day, invoices_list = await asyncio.gather(
        analytics_service.get_summary(target_ids, periodo, tipo_operacion, db),
        analytics_service.get_top_suppliers(target_ids, periodo, 5, tipo_operacion, db),
        analytics_service.get_ai_classification(target_ids, periodo, tipo_operacion, db),
        analytics_service.get_invoices_by_day(target_ids, periodo, tipo_operacion, db),
        analytics_service.get_invoices_list(target_ids, periodo, tipo_operacion, db)
    )

    return {
        "summary": summary,
        "top_suppliers": top_suppliers,
        "ai_classification": ai_classification,
        "invoices_by_day": invoices_by_day,
        "invoices_list": invoices_list
    }
