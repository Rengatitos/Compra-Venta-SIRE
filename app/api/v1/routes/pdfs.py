import csv
import io
import logging
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.background import BackgroundTask

from app.api.v1.deps import empresa_actual, empresa_id, libro_valido, periodo_valido
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.domain.jobs import TipoJob
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import periodos as repo_periodos
from app.schemas.job import JobAceptado
from app.services import almacen_pdf, jobs_service, pdf_service

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

# Cuántos comprobantes se leen para armar el manifiesto. Mismo techo que usa
# `exportar_lote` para el Excel de la plantilla.
MAX_FILAS_MANIFIESTO = 5000

CABECERA_MANIFIESTO = (
    "serie_numero",
    "tipo_cp",
    "fecha_emision",
    "documento_contraparte",
    "razon_social",
    "total",
    "ruta_pdf",
    "estado",
)


@router.post(
    "",
    response_model=JobAceptado,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Descargar el PDF de los comprobantes desde SUNAT",
)
@limiter.limit("5/minute")
async def iniciar_descarga(
    request: Request,
    background_tasks: BackgroundTasks,
    periodo: str = Depends(periodo_valido),
    libro: Libro = Depends(libro_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    duplicado = await jobs_service.activo(
        db, empresa["ruc"], TipoJob.DESCARGA_PDFS, periodo=periodo, libro=libro
    )
    if duplicado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya hay una descarga de PDFs de {libro.value} en curso para el periodo "
                f"{periodo}. Espera a que termine (job {duplicado.job_id})."
            ),
        )

    job = await jobs_service.crear(db, TipoJob.DESCARGA_PDFS, empresa["ruc"], periodo, libro)

    async def tarea(reportar):
        return await pdf_service.descargar(db, empresa, periodo, libro, reportar)

    # El cuarto argumento es la cola. Va el RUC porque este trabajo comparte la
    # sesión SOL con la extracción de detalle, que es única por usuario: sin el
    # candado los dos abren Chromium a la vez y SUNAT invalida una de las dos.
    background_tasks.add_task(jobs_service.ejecutar, db, job.job_id, tarea, empresa["ruc"])

    logger.info(
        "Descarga de PDFs encolada ruc=%s periodo=%s libro=%s job_id=%s",
        empresa["ruc"],
        periodo,
        libro.value,
        job.job_id,
    )

    return {
        "job_id": job.job_id,
        "estado": job.estado.value,
        "mensaje": (
            f"Descarga de PDFs de {libro.value} iniciada. "
            f"Consulta su avance en /api/v1/jobs/{job.job_id}"
        ),
    }


def _manifiesto(filas: list[dict]) -> bytes:
    """CSV que relaciona cada comprobante con su respaldo.

    Es lo que convierte el ZIP en algo auditable: sin él, el auditor recibe una
    carpeta de PDFs sin forma de cruzarlos con el registro. Va con BOM porque
    lo va a abrir Excel, que sin él parte las tildes.
    """
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(CABECERA_MANIFIESTO)

    for fila in filas:
        pdf = fila.get("pdf_sunat") or {}
        fecha = fila.get("fecha_emision")
        escritor.writerow(
            [
                fila.get("serie_numero", ""),
                fila.get("tipo_cp", ""),
                fecha.date().isoformat() if hasattr(fecha, "date") else (fecha or ""),
                fila.get("documento_contraparte", ""),
                fila.get("razon_social", ""),
                fila.get("total", ""),
                pdf.get("ruta", ""),
                "descargado" if pdf.get("ruta") else "sin_pdf",
            ]
        )

    return salida.getvalue().encode("utf-8-sig")


def _armar_zip(pdfs: list[Path], base: Path, manifiesto: bytes) -> str:
    """Escribe el ZIP en un temporal y devuelve su ruta.

    Aquí se rompe a propósito la convención del repo de devolver los binarios
    con `io.BytesIO`: un periodo de ventas son cientos de boletas y el ZIP pasa
    de decenas de MB, mientras el contenedor corre con un solo worker y
    `MALLOC_ARENA_MAX=2`. Con un temporal el pico de memoria es un búfer, no el
    archivo entero.
    """
    temporal = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    try:
        with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zf:
            for pdf in pdfs:
                # Se conserva la jerarquía dentro del periodo (facturas/,
                # boletas/, …), que es lo que el auditor espera navegar.
                zf.write(pdf, arcname=pdf.relative_to(base).as_posix())
            zf.writestr("manifiesto.csv", manifiesto)
    finally:
        temporal.close()
    return temporal.name


@router.get(
    "/zip",
    summary="Descargar en ZIP los PDFs ya guardados del periodo",
    response_class=StreamingResponse,
)
async def exportar_zip(
    periodo: str = Depends(periodo_valido),
    libro: Libro = Depends(libro_valido),
    empresa: dict = Depends(empresa_actual),
    empresa_pk: str = Depends(empresa_id),
    limite: int = Query(
        MAX_FILAS_MANIFIESTO, ge=1, le=MAX_FILAS_MANIFIESTO, description="Filas del manifiesto"
    ),
    db=Depends(get_db),
):
    if not await repo_periodos.obtener(db, empresa_pk, periodo):
        raise HTTPException(status_code=404, detail="Periodo no encontrado para esta empresa")

    base = almacen_pdf.raiz_periodo(empresa["ruc"], libro, periodo)
    pdfs = almacen_pdf.listar(empresa["ruc"], libro, periodo)
    if not pdfs:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No hay PDFs guardados de {libro.value} en el periodo {periodo}. "
                "Ejecuta primero la descarga de PDFs."
            ),
        )

    filas = await repo_comprobantes.listar(db, empresa_pk, periodo, libro=libro, limit=limite)
    ruta_zip = _armar_zip(pdfs, base, _manifiesto(filas))

    nombre = f"pdfs_{libro.value}_{periodo}.zip"
    logger.info(
        "ZIP de PDFs servido ruc=%s periodo=%s libro=%s archivos=%s",
        empresa["ruc"],
        periodo,
        libro.value,
        len(pdfs),
    )
    return StreamingResponse(
        open(ruta_zip, "rb"),  # noqa: SIM115 — lo cierra StreamingResponse al terminar
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
        # Sin esto el temporal se queda en disco después de cada descarga.
        background=BackgroundTask(os.unlink, ruta_zip),
    )
