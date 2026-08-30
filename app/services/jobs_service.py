from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.comprobante import Libro
from app.domain.jobs import EstadoJob, Job, Progreso, TipoJob
from app.repositories import jobs as repo_jobs

logger = logging.getLogger(__name__)

# Una función que recibe un reportador de progreso y devuelve el resultado.
Reportador = Callable[[int, int, str], Awaitable[None]]
Tarea = Callable[[Reportador], Awaitable[dict[str, Any]]]


async def crear(
    db: AsyncIOMotorDatabase,
    tipo: TipoJob,
    ruc: str,
    periodo: str,
    libro: Libro | None = None,
) -> Job:
    return await repo_jobs.crear(
        db, Job(tipo=tipo, ruc=ruc, periodo=periodo, libro=libro)
    )


async def obtener(db: AsyncIOMotorDatabase, job_id: str) -> Job | None:
    return await repo_jobs.obtener(db, job_id)


async def listar(
    db: AsyncIOMotorDatabase,
    ruc: str,
    *,
    periodo: str | None = None,
    tipo: TipoJob | None = None,
    estado: EstadoJob | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[Job]:
    return await repo_jobs.listar(
        db, ruc, periodo=periodo, tipo=tipo, estado=estado, limit=limit, skip=skip
    )


async def activo(
    db: AsyncIOMotorDatabase, ruc: str, tipo: TipoJob
) -> Job | None:
    """Devuelve el trabajo de ese tipo que siga vivo para la empresa, si lo hay.

    El scraping abre un Chromium por trabajo y la API corre con un solo worker,
    así que dos extracciones a la vez se pelean por la RAM y por la sesión SOL,
    que es única por usuario.
    """
    for estado in (EstadoJob.EN_PROGRESO, EstadoJob.PENDIENTE):
        vivos = await repo_jobs.listar(db, ruc, tipo=tipo, estado=estado, limit=1)
        if vivos:
            return vivos[0]
    return None


async def ejecutar(db: AsyncIOMotorDatabase, job_id: str, tarea: Tarea) -> None:
    async def reportar(actual: int, total: int, mensaje: str = "") -> None:
        await repo_jobs.actualizar(
            db, job_id, progreso=Progreso(actual=actual, total=total, mensaje=mensaje)
        )

    await repo_jobs.actualizar(db, job_id, estado=EstadoJob.EN_PROGRESO)

    try:
        resultado = await tarea(reportar)
    except Exception as exc:
        logger.exception("Job fallido job_id=%s", job_id)
        await repo_jobs.actualizar(db, job_id, estado=EstadoJob.FALLIDO, error=str(exc))
        return

    await repo_jobs.actualizar(
        db, job_id, estado=EstadoJob.COMPLETADO, resultado=resultado
    )
    logger.info("Job completado job_id=%s", job_id)


def serializar(job: Job) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "tipo": job.tipo.value,
        "estado": job.estado.value,
        "ruc": job.ruc,
        "periodo": job.periodo,
        "libro": job.libro.value if job.libro else None,
        "progreso": {
            "actual": job.progreso.actual,
            "total": job.progreso.total,
            "mensaje": job.progreso.mensaje,
            "porcentaje": job.progreso.porcentaje,
        },
        "resultado": job.resultado,
        "error": job.error,
        "creado_en": job.creado_en,
        "actualizado_en": job.actualizado_en,
    }
