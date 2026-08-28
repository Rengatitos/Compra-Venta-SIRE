from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories._mongo import NOMBRE_COL_EMPRESAS


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_EMPRESAS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index("ruc", unique=True)


def a_object_id(empresa_id: str) -> ObjectId | None:
    try:
        return ObjectId(empresa_id)
    except Exception:
        return None


async def crear(db: AsyncIOMotorDatabase, datos: dict[str, Any]) -> dict[str, Any]:
    documento = {
        **datos,
        "fecha_creacion": datetime.now(UTC).isoformat(),
    }
    resultado = await _col(db).insert_one(documento)
    return await _col(db).find_one({"_id": resultado.inserted_id})


async def obtener_por_id(db: AsyncIOMotorDatabase, empresa_id: str) -> dict[str, Any] | None:
    oid = a_object_id(empresa_id)
    if oid is None:
        return None
    return await _col(db).find_one({"_id": oid})


async def obtener_por_ruc(db: AsyncIOMotorDatabase, ruc: str) -> dict[str, Any] | None:
    return await _col(db).find_one({"ruc": ruc})


async def listar(db: AsyncIOMotorDatabase, limit: int = 100) -> list[dict[str, Any]]:
    return await _col(db).find().to_list(length=limit)


async def listar_ids_por_rucs(db: AsyncIOMotorDatabase, rucs: list[str]) -> list[str]:
    empresas = await _col(db).find({"ruc": {"$in": rucs}}).to_list(length=None)
    return [str(e["_id"]) for e in empresas]


async def actualizar(
    db: AsyncIOMotorDatabase, empresa_id: ObjectId, cambios: dict[str, Any]
) -> dict[str, Any] | None:
    if cambios:
        await _col(db).update_one({"_id": empresa_id}, {"$set": cambios})
    return await _col(db).find_one({"_id": empresa_id})


async def guardar_token_sunat(
    db: AsyncIOMotorDatabase, empresa_id: ObjectId, token: str
) -> None:
    await _col(db).update_one({"_id": empresa_id}, {"$set": {"sunat_token": token}})


async def eliminar(db: AsyncIOMotorDatabase, empresa_id: ObjectId) -> int:
    resultado = await _col(db).delete_one({"_id": empresa_id})
    return resultado.deleted_count
