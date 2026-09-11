import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.v1.deps import empresa_actual, empresa_id, periodo_valido
from app.db.database import get_db
from app.repositories import periodos as repo_periodos
from app.services import reporte_asociado

router = APIRouter()


async def _cargar_registros(db, empresa, empresa_pk, periodo):
    if not await repo_periodos.obtener(db, empresa_pk, periodo):
        raise HTTPException(status_code=404, detail="Periodo no encontrado para esta empresa")
    return await reporte_asociado.registros(db, empresa, periodo)


@router.get("/reporte-asociado/estado", summary="Consultar si el reporte asociado está listo")
async def estado_reporte_asociado(
    periodo: str = Depends(periodo_valido),
    empresa: dict = Depends(empresa_actual),
    empresa_pk: str = Depends(empresa_id),
    db=Depends(get_db),
):
    registros = await _cargar_registros(db, empresa, empresa_pk, periodo)
    return reporte_asociado.estado(registros)


@router.get("/reporte-asociado", summary="Descargar reporte y comprobantes asociados")
async def descargar_reporte_asociado(
    periodo: str = Depends(periodo_valido),
    empresa: dict = Depends(empresa_actual),
    empresa_pk: str = Depends(empresa_id),
    db=Depends(get_db),
):
    registros = await _cargar_registros(db, empresa, empresa_pk, periodo)
    if not reporte_asociado.estado(registros)["habilitado"]:
        raise HTTPException(
            status_code=409,
            detail="Completa las glosas de compras y ventas antes de descargar",
        )
    ruta = reporte_asociado.zip_reporte(registros, periodo, empresa["ruc"], empresa["usuario"])
    return FileResponse(
        ruta,
        media_type="application/zip",
        filename=f'{reporte_asociado.nombre(empresa["usuario"], periodo)}.zip',
        background=BackgroundTask(os.unlink, ruta),
    )