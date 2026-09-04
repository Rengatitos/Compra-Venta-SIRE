import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_id
from app.db.database import get_db
from app.repositories import plan_cuentas as repo_plan_cuentas
from app.schemas.generic import StatusResponse
from app.schemas.plan_cuentas import CargaResponse, PlanCuentasResponse
from app.services import plan_cuentas_service
from app.services.plan_cuentas_service import ExcelInvalido

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

EXTENSIONES = (".xlsx", ".xlsm")


@router.get("", response_model=PlanCuentasResponse, summary="Consultar el maestro de cuentas")
async def listar_cuentas(
    busqueda: str | None = Query(
        None, description="Filtra por código o por descripción, sin distinguir mayúsculas"
    ),
    limit: int = Query(100, ge=1, le=3000),
    skip: int = Query(0, ge=0),
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    cuentas = await repo_plan_cuentas.listar(db, empresa, busqueda, skip=skip, limit=limit)
    total = await repo_plan_cuentas.contar(db, empresa, busqueda)
    return {
        "cuentas": [repo_plan_cuentas.desde_documento(d).model_dump() for d in cuentas],
        "total": total,
    }


@router.post("", response_model=CargaResponse, summary="Cargar el maestro de cuentas")
@limiter.limit("5/minute")
async def cargar_cuentas(
    request: Request,
    archivo: UploadFile = File(...),
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    """Reemplaza el maestro completo de la empresa con el Excel de Contasis.

    Se reemplaza y no se fusiona: el archivo es la fuente de verdad, y una
    cuenta que Contasis dejó de exportar es una cuenta que ya no existe.
    """
    if not archivo.filename or not archivo.filename.lower().endswith(EXTENSIONES):
        raise HTTPException(
            status_code=400,
            detail=f"Solo se permiten archivos Excel ({', '.join(EXTENSIONES)})",
        )

    contenido = await archivo.read()

    try:
        # Son casi tres mil filas: en el hilo del loop bloquearía la API el
        # tiempo que tarde openpyxl en recorrerlas.
        cuentas = await asyncio.to_thread(plan_cuentas_service.desde_excel, contenido)
    except ExcelInvalido as fallo:
        raise HTTPException(status_code=400, detail=str(fallo)) from fallo

    total = await repo_plan_cuentas.reemplazar(db, empresa, cuentas)
    logger.info(
        "Maestro de cuentas cargado empresa_id=%s archivo=%s cuentas=%s",
        empresa,
        archivo.filename,
        total,
    )
    return {"mensaje": f"Maestro de cuentas cargado desde «{archivo.filename}»", "cuentas": total}


@router.delete("", response_model=StatusResponse, summary="Borrar el maestro de cuentas")
async def eliminar_cuentas(empresa: str = Depends(empresa_id), db=Depends(get_db)):
    borradas = await repo_plan_cuentas.eliminar_de_empresa(db, empresa)
    return {
        "estado": "exito",
        "mensaje": f"Se borraron {borradas} cuentas",
        "datos": {"cuentas": borradas},
    }
