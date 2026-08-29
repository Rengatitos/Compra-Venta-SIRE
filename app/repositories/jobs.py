from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.jobs import EstadoJob, Job, Progreso, TipoJob
from app.repositories._mongo import NOMBRE_COL_JOBS


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_JOBS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index("job_id", unique=True)
    await _col(db).create_index([("ruc", 1), ("periodo", 1)])
    # El historial se lee siempre por empresa y de lo mas reciente a lo mas
    # antiguo: sin este indice el sort se resuelve en memoria.
    await _col(db).create_index([("ruc", 1), ("creado_en", -1)])


def a_documento(job: Job) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "tipo": job.tipo.value,
        "estado": job.estado.value,
        "ruc": job.ruc,
        "periodo": job.periodo,
        "libro": job.libro.value if job.libro else None,
        "progreso": job.progreso.model_dump(),
        "resultado": job.resultado,
        "error": job.error,
        "creado_en": job.creado_en,
        "actualizado_en": job.actualizado_en,
    }


def desde_documento(documento: dict[str, Any]) -> Job:
    return Job(
        job_id=documento["job_id"],
        tipo=documento["tipo"],
        estado=documento["estado"],
        ruc=documento["ruc"],
        periodo=documento["periodo"],
        libro=documento.get("libro"),
        progreso=Progreso(**(documento.get("progreso") or {})),
        resultado=documento.get("resultado"),
        error=documento.get("error"),
        creado_en=documento["creado_en"],
        actualizado_en=documento["actualizado_en"],
    )


async def crear(db: AsyncIOMotorDatabase, job: Job) -> Job:
    await _col(db).insert_one(a_documento(job))
    return job


async def obtener(db: AsyncIOMotorDatabase, job_id: str) -> Job | None:
    documento = await _col(db).find_one({"job_id": job_id})
    return desde_documento(documento) if documento else None


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
    """Historial de trabajos de una empresa, del mas reciente al mas antiguo."""
    filtro: dict[str, Any] = {"ruc": ruc}
    if periodo:
        filtro["periodo"] = periodo
    if tipo:
        filtro["tipo"] = tipo.value
    if estado:
        filtro["estado"] = estado.value

    cursor = _col(db).find(filtro).sort("creado_en", -1).skip(skip).limit(limit)
    return [desde_documento(documento) async for documento in cursor]


async def actualizar(
    db: AsyncIOMotorDatabase,
    job_id: str,
    *,
    estado: EstadoJob | None = None,
    progreso: Progreso | None = None,
    resultado: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    cambios: dict[str, Any] = {"actualizado_en": datetime.now(UTC)}
    if estado is not None:
        cambios["estado"] = estado.value
    if progreso is not None:
        cambios["progreso"] = progreso.model_dump()
    if resultado is not None:
        cambios["resultado"] = resultado
    if error is not None:
        cambios["error"] = error
    await _col(db).update_one({"job_id": job_id}, {"$set": cambios})
