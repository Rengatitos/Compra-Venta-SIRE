import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual, periodo_valido
from app.db.database import get_db
from app.repositories import comprobantes as repo
from app.repositories import periodos as repo_periodos
from app.schemas.job import JobAceptado
from app.services import almacen_pdf, detracciones_service
from app.services.comprobante_service import _tiene_detraccion

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/disponibilidad")
async def disponibilidad(
    periodo: str = Depends(periodo_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    documentos = await repo.listar_todos_compras(db, str(empresa["_id"]), periodo)
    return {"disponible": any(_tiene_detraccion(doc) for doc in documentos)}


@router.post("", response_model=JobAceptado, status_code=202)
@limiter.limit("5/minute")
async def iniciar(
    request: Request,
    background_tasks: BackgroundTasks,
    periodo: str = Depends(periodo_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    job = await detracciones_service.encolar(db, empresa, periodo, background_tasks)
    return {
        "job_id": job.job_id,
        "estado": job.estado.value,
        "mensaje": "Consulta de detracciones encolada",
    }


@router.get("/zip")
async def descargar(
    periodo: str = Depends(periodo_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    datos = await listar_npds(periodo, empresa, db)
    if not datos["npds"]:
        raise HTTPException(404, "No hay NPD descargados para este periodo")
    try:
        contenido = await asyncio.to_thread(detracciones_service.armar_zip, datos["npds"])
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return Response(
        contenido,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="detracciones_{periodo}.zip"'},
    )


@router.get("/npds")
async def listar_npds(
    periodo: str = Depends(periodo_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    documento = await repo_periodos.obtener(db, str(empresa["_id"]), periodo)
    if documento is None:
        raise HTTPException(404, "El periodo no existe para esta empresa")
    return {"npds": documento.get("npds", []), "consultado_en": documento.get("npds_consultado_en")}


@router.get("/npds/{numero}/pdf")
async def descargar_pdf_npd(
    numero: str,
    periodo: str = Depends(periodo_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    if not numero.isdigit():
        raise HTTPException(422, "Número NPD inválido")
    datos = await listar_npds(periodo, empresa, db)
    npd = next((n for n in datos["npds"] if n["numero"] == numero), None)
    if not npd or not npd.get("pdf_ruta"):
        raise HTTPException(404, "El PDF de este NPD no está disponible")
    archivo = almacen_pdf.absoluta(npd["pdf_ruta"])
    if not archivo.is_file():
        raise HTTPException(404, "El PDF de este NPD no está disponible")
    return FileResponse(archivo, media_type="application/pdf", filename=f"npd_{numero}.pdf")
