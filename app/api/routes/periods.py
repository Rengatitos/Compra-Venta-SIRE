from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime
from app.schemas.period import PeriodCreate, PeriodResponse, PeriodUpdate
from app.db.database import get_db
from app.core.auth import require_same_user

router = APIRouter()

@router.post("/", response_model=PeriodResponse)
async def create_period(user_id: str, period: PeriodCreate, db = Depends(get_db), user = Depends(require_same_user)):
    periods_col = db["periodos"]
    existing_period = await periods_col.find_one({"user_id": user_id, "periodo": period.periodo})
    if existing_period:
        raise HTTPException(status_code=400, detail="El periodo ya existe para este usuario")

    new_status = "pendiente"
    new_period = {
        "user_id": user_id,
        "periodo": period.periodo,
        "estado": new_status,
        "fecha_creacion": datetime.now().isoformat()
    }
    await periods_col.insert_one(new_period)
    return {"periodo": period.periodo, "estado": new_status}

@router.get("/", response_model=List[PeriodResponse])
async def list_periods(user_id: str, db = Depends(get_db), user = Depends(require_same_user)):
    periods_col = db["periodos"]
    user_periods = await periods_col.find({"user_id": user_id}).to_list(length=100)
    return [{"periodo": p["periodo"], "estado": p["estado"]} for p in user_periods]

@router.get("/{periodo}", response_model=PeriodResponse)
async def get_period(user_id: str, periodo: str, db = Depends(get_db), user = Depends(require_same_user)):
    periods_col = db["periodos"]
    period_obj = await periods_col.find_one({"user_id": user_id, "periodo": periodo})
    if not period_obj:
        raise HTTPException(status_code=404, detail="Periodo no encontrado")
    return {"periodo": period_obj["periodo"], "estado": period_obj["estado"]}

@router.put("/{periodo}", response_model=PeriodResponse)
async def update_period(user_id: str, periodo: str, update_data: PeriodUpdate, db = Depends(get_db), user = Depends(require_same_user)):
    periods_col = db["periodos"]
    existing_period = await periods_col.find_one({"user_id": user_id, "periodo": periodo})

    if not existing_period:
        raise HTTPException(status_code=404, detail="Periodo no encontrado")

    if update_data.estado:
        await periods_col.update_one(
            {"user_id": user_id, "periodo": periodo},
            {"$set": {"estado": update_data.estado}}
        )
        return {"periodo": periodo, "estado": update_data.estado}

    return {"periodo": existing_period["periodo"], "estado": existing_period["estado"]}

@router.delete("/{periodo}")
async def delete_period(user_id: str, periodo: str, db = Depends(get_db), user = Depends(require_same_user)):
    facturas_col = db["facturas"]
    await facturas_col.delete_many({"user_id": user_id, "periodo": periodo})

    periods_col = db["periodos"]
    result = await periods_col.delete_one({"user_id": user_id, "periodo": periodo})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Periodo no encontrado")

    return {"mensaje": "Periodo eliminado exitosamente"}
