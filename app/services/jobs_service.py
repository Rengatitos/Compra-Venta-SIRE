from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.comprobante import Libro
from app.domain.jobs import EstadoJob, Job, TipoJob
from app.repositories import jobs as repo_jobs

logger = logging.getLogger(__name__)

# Una función que recibe un reportador de progreso y devuelve el resultado.
Reportador = Callable[[int, int, str], Awaitable[None]]


async def crear(
    db: AsyncIOMotorDatabase,
    tipo: TipoJob,
    ruc: str,
    periodo: str,
    libro: Libro | None = None,
) -> Job:
    """Un job de solo historial: nadie lo ejecuta, lo cierra quien lo creó.

    Los trabajos en segundo plano se crean con `app.services.cola.encolar`.
    """
    return await repo_jobs.crear(
        db, Job(tipo=tipo, ruc=ruc, periodo=periodo, libro=libro)
    )


async def obtener(db: AsyncIOMotorDatabase, job_id: str) -> Job | None:
    return await repo_jobs.obtener(db, job_id)


async def listar(
    db: AsyncIOMotorDatabase,
    ruc: str | None = None,
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


# Exclusión corta dentro del proceso para «comprobar y crear» sin carreras (dos
# peticiones que encolan lo mismo a la vez). La ejecución de los trabajos ya no
# pasa por aquí: la serializa por carril la cola durable (`app.services.cola`).
_candados: dict[str, asyncio.Lock] = {}


def candado(nombre: str) -> asyncio.Lock:
    existente = _candados.get(nombre)
    if existente is None:
        existente = asyncio.Lock()
        _candados[nombre] = existente
    return existente


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
        "gestionado": job.gestionado,
        "solicitud_id": job.solicitud_id,
        "intentos": job.intentos,
        "max_intentos": job.max_intentos,
        "ultimo_intento_en": job.ultimo_intento_en,
        "siguiente_intento_en": job.siguiente_intento_en,
        "historial_errores": [
            {
                "intento": registro.get("intento"),
                "en": registro.get("en"),
                "error": registro.get("error", ""),
            }
            for registro in job.historial_errores
        ],
    }
