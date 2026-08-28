from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories._mongo import NOMBRE_COL_PERIODOS


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_PERIODOS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index([("empresa_id", 1), ("periodo", 1)], unique=True)


async def crear(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, estado: str = "pendiente"
) -> dict[str, Any]:
    documento = {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "estado": estado,
        "fecha_creacion": datetime.now(UTC).isoformat(),
    }
    await _col(db).insert_one(documento)
    return documento


async def obtener(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str
) -> dict[str, Any] | None:
    return await _col(db).find_one({"empresa_id": empresa_id, "periodo": periodo})


async def listar(
    db: AsyncIOMotorDatabase, empresa_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    return await _col(db).find({"empresa_id": empresa_id}).to_list(length=limit)


async def actualizar_estado(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, estado: str
) -> None:
    await _col(db).update_one(
        {"empresa_id": empresa_id, "periodo": periodo},
        {"$set": {"estado": estado}},
    )


async def eliminar(db: AsyncIOMotorDatabase, empresa_id: str, periodo: str) -> int:
    resultado = await _col(db).delete_one({"empresa_id": empresa_id, "periodo": periodo})
    return resultado.deleted_count


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count
