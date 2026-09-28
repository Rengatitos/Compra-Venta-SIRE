"""Cola durable de trabajos en segundo plano.

Un trabajo es un documento de la colección `jobs` con todo lo necesario para
ejecutarlo (`tipo`, empresa, periodo, libro y `parametros`). El worker
(`app.services.cola.worker`) los toma de Mongo, así que el contador puede
cerrar la página y la API reiniciarse sin que se pierdan: lo pendiente sigue
pendiente y lo que estaba en curso vuelve a la cola.

Cada trabajo va en un carril (`cola`). Dos trabajos del mismo carril no corren
a la vez; los de carriles distintos, sí. El carril de lo que entra al portal
SOL es el RUC, porque la sesión SOL es única por usuario.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.domain.comprobante import Libro
from app.domain.jobs import Job, Progreso, TipoJob
from app.repositories import jobs as repo_jobs
from app.services.cola.errores import ErrorPermanente, ErrorTransitorio

__all__ = ["ErrorPermanente", "ErrorTransitorio", "carril_sol", "encolar"]

CARRIL_CLASIFICADOR = "clasificador"


def carril_sol(ruc: str) -> str:
    """Carril de lo que usa la sesión SOL de una empresa."""
    return ruc


async def encolar(
    db: AsyncIOMotorDatabase,
    tipo: TipoJob,
    ruc: str,
    periodo: str,
    libro: Libro | None = None,
    *,
    cola: str | None,
    parametros: dict[str, Any] | None = None,
    solicitud_id: str | None = None,
    max_intentos: int | None = None,
) -> Job:
    """Deja el trabajo en Mongo como pendiente y avisa al worker."""
    job = Job(
        tipo=tipo,
        ruc=ruc,
        periodo=periodo,
        libro=libro,
        gestionado=True,
        cola=cola,
        parametros=parametros or {},
        solicitud_id=solicitud_id,
        max_intentos=max_intentos or settings.COLA_MAX_INTENTOS,
        siguiente_intento_en=datetime.now(UTC),
        progreso=Progreso(mensaje="En cola"),
    )
    await repo_jobs.crear(db, job)

    # Importado aquí: el worker importa los servicios que ejecuta, y alguno de
    # ellos encola trabajos a su vez.
    from app.services.cola import worker

    worker.despertar()
    return job
