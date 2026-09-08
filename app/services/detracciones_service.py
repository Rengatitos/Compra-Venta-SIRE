from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import UTC, datetime

from app.domain.comprobante import Libro
from app.domain.jobs import TipoJob
from app.repositories import periodos as repo_periodos
from app.services import almacen_pdf, jobs_service
from app.services.sunat import detracciones


async def consultar(db, empresa, periodo, reportar):
    empresa_id = str(empresa["_id"])
    if not await repo_periodos.obtener(db, empresa_id, periodo):
        raise ValueError("El periodo no existe para esta empresa")
    await reportar(0, 1, "Consultando NPD del periodo en SUNAT")
    loop = asyncio.get_running_loop()

    def progreso(mensaje):
        asyncio.run_coroutine_threadsafe(reportar(0, 1, mensaje), loop).result(timeout=30)

    datos = await detracciones.obtener(empresa, periodo, progreso)
    npds = datos["npds"]
    await repo_periodos.guardar_npds(db, empresa_id, periodo, npds, datetime.now(UTC).isoformat())
    await reportar(1, 1, f"Consulta terminada: {len(npds)} NPD del periodo")
    return {
        "npds_consultados": len(npds),
        "pdfs_descargados": sum(bool(n.get("pdf_ruta")) for n in npds),
    }


async def encolar(db, empresa, periodo, background_tasks):
    async with jobs_service._cola(f"encolar-detracciones:{empresa['ruc']}:{periodo}"):
        return await _encolar(db, empresa, periodo, background_tasks)


async def _encolar(db, empresa, periodo, background_tasks):
    existente = await jobs_service.activo(
        db, empresa["ruc"], TipoJob.DETRACCIONES, periodo=periodo, libro=Libro.COMPRAS
    )
    if existente:
        return existente
    job = await jobs_service.crear(db, TipoJob.DETRACCIONES, empresa["ruc"], periodo, Libro.COMPRAS)

    async def tarea(reportar):
        return await consultar(db, empresa, periodo, reportar)

    background_tasks.add_task(jobs_service.ejecutar, db, job.job_id, tarea, empresa["ruc"])
    return job


def armar_zip(npds):
    contenido = io.BytesIO()
    cantidad = 0
    with zipfile.ZipFile(contenido, "w", zipfile.ZIP_DEFLATED) as archivo:
        for npd in npds:
            numero = str(npd["numero"])
            if not numero.isdigit():
                raise ValueError("Numero NPD invalido")
            if npd.get("pdf_ruta"):
                pdf = almacen_pdf.absoluta(npd["pdf_ruta"])
                if pdf.is_file():
                    archivo.write(pdf, arcname=f"npd_{numero}.pdf")
                    cantidad += 1
    if not cantidad:
        raise FileNotFoundError("No hay PDF de NPD disponibles para este periodo")
    return contenido.getvalue()
