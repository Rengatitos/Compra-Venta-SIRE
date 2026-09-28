"""Cargas de empresas: una por alta individual o por Excel subido.

Es el registro de trazabilidad del alta: quién la hizo, cuándo, y qué pasó con
cada fila. Nunca guarda contraseñas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.carga_empresas import ESTADOS_FILA_TERMINALES, EstadoCarga, EstadoFila
from app.repositories._mongo import NOMBRE_COL_CARGAS_EMPRESAS
from app.repositories.empresas import a_object_id


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_CARGAS_EMPRESAS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index([("creado_en", -1)])


async def crear(db: AsyncIOMotorDatabase, documento: dict[str, Any]) -> str:
    resultado = await _col(db).insert_one(documento)
    return str(resultado.inserted_id)


async def obtener(db: AsyncIOMotorDatabase, carga_id: str) -> dict[str, Any] | None:
    oid = a_object_id(carga_id)
    if oid is None:
        return None
    return await _col(db).find_one({"_id": oid})


async def listar(db: AsyncIOMotorDatabase, limit: int = 50) -> list[dict[str, Any]]:
    cursor = _col(db).find({}, {"filas": 0}).sort("creado_en", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def guardar_fila(
    db: AsyncIOMotorDatabase, carga_id: str, fila: int, cambios: dict[str, Any]
) -> None:
    """Actualiza una fila y, si ya no queda ninguna pendiente, cierra la carga."""
    oid = a_object_id(carga_id)
    if oid is None:
        return
    await _col(db).update_one(
        {"_id": oid, "filas.fila": fila},
        {"$set": {f"filas.$.{campo}": valor for campo, valor in cambios.items()}},
    )
    await recalcular(db, carga_id)


async def recalcular(db: AsyncIOMotorDatabase, carga_id: str) -> None:
    carga = await obtener(db, carga_id)
    if carga is None:
        return
    filas = carga.get("filas") or []
    terminadas = sum(1 for f in filas if EstadoFila(f["estado"]) in ESTADOS_FILA_TERMINALES)
    completa = terminadas == len(filas)
    cambios: dict[str, Any] = {
        "progreso": {
            "actual": terminadas,
            "total": len(filas),
            "mensaje": "Registro terminado" if completa else f"{terminadas} de {len(filas)} filas",
        },
        "estado": (EstadoCarga.COMPLETADA if completa else EstadoCarga.EN_PROGRESO).value,
    }
    if completa and not carga.get("terminado_en"):
        cambios["terminado_en"] = datetime.now(UTC)
    await _col(db).update_one({"_id": carga["_id"]}, {"$set": cambios})
