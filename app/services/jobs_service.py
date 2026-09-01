from __future__ import annotations

import asyncio
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
    db: AsyncIOMotorDatabase,
    ruc: str,
    tipo: TipoJob,
    *,
    periodo: str | None = None,
    libro: Libro | None = None,
) -> Job | None:
    """El trabajo de ese tipo que siga vivo, si lo hay.

    Sin `periodo` ni `libro` responde por toda la empresa —sirve para saber si
    algo va a tener que esperar—; con ellos acota a esa combinación, que es lo
    que decide si una petición es un duplicado.
    """
    for estado in (EstadoJob.EN_PROGRESO, EstadoJob.PENDIENTE):
        vivos = await repo_jobs.listar(
            db, ruc, periodo=periodo, libro=libro, tipo=tipo, estado=estado, limit=1
        )
        if vivos:
            return vivos[0]
    return None


# Una cola por empresa. El scraping abre un Chromium y entra con la sesión SOL,
# que es única por usuario: dos extracciones a la vez se pelean por ella y
# SUNAT acaba invalidando una de las dos. En vez de rechazar la segunda, se
# encola —el trabajo se acepta, se queda en `pendiente` y arranca solo cuando
# el anterior termina—, que es lo que permite lanzar compras y ventas seguidas.
#
# El candado vive en el proceso, y eso basta porque la API corre con un único
# worker (ver el Dockerfile). Con varias réplicas haría falta un candado en
# Mongo; hasta entonces, esto es lo proporcionado.
_colas: dict[str, asyncio.Lock] = {}


def _cola(nombre: str) -> asyncio.Lock:
    candado = _colas.get(nombre)
    if candado is None:
        candado = asyncio.Lock()
        _colas[nombre] = candado
    return candado


async def ejecutar(
    db: AsyncIOMotorDatabase, job_id: str, tarea: Tarea, cola: str | None = None
) -> None:
    async def reportar(actual: int, total: int, mensaje: str = "") -> None:
        await repo_jobs.actualizar(
            db, job_id, progreso=Progreso(actual=actual, total=total, mensaje=mensaje)
        )

    if cola is None:
        await _correr(db, job_id, tarea, reportar)
        return

    candado = _cola(cola)
    if candado.locked():
        # El trabajo ya está aceptado y visible; decir que espera evita que
        # parezca colgado en `pendiente` sin explicación.
        await reportar(0, 0, "En cola: hay otra extracción en curso")
        logger.info("Job en cola job_id=%s cola=%s", job_id, cola)

    async with candado:
        await _correr(db, job_id, tarea, reportar)


async def _correr(
    db: AsyncIOMotorDatabase, job_id: str, tarea: Tarea, reportar: Reportador
) -> None:
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
