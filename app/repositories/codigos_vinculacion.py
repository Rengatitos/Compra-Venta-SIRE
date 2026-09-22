"""Códigos de un solo uso con los que un dispositivo de sire-bot se vincula a una empresa.

Solo se guarda el sha256 del código, nunca el código en claro. El TTL sobre
`expira_en` hace que Mongo borre solos los vencidos; los canjeados se quedan
hasta entonces para poder distinguir "ya se usó" (409) de "no existe" (400).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.repositories._mongo import NOMBRE_COL_CODIGOS_VINCULACION


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_CODIGOS_VINCULACION]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    col = _col(db)
    await col.create_index("expira_en", expireAfterSeconds=0, name="ttl_expira_en")
    await col.create_index([("ruc", 1), ("codigo_hash", 1)], unique=True, name="uniq_ruc_codigo")


async def invalidar_activos(db: AsyncIOMotorDatabase, ruc: str) -> int:
    """Borra los códigos aún no canjeados: solo vale el último que se generó."""
    resultado = await _col(db).delete_many({"ruc": ruc, "usado_en": None})
    return resultado.deleted_count


async def crear(db: AsyncIOMotorDatabase, documento: dict[str, Any]) -> None:
    await _col(db).insert_one(documento)


async def canjear(
    db: AsyncIOMotorDatabase,
    ruc: str,
    codigo_hash: str,
    dispositivo_id: str,
    ahora: datetime,
) -> dict[str, Any] | None:
    """Marca el código como usado en una sola operación atómica, si sigue vigente."""
    return await _col(db).find_one_and_update(
        {
            "ruc": ruc,
            "codigo_hash": codigo_hash,
            "usado_en": None,
            "expira_en": {"$gt": ahora},
        },
        {"$set": {"usado_en": ahora, "dispositivo_id": dispositivo_id}},
        return_document=ReturnDocument.AFTER,
    )


async def buscar(db: AsyncIOMotorDatabase, ruc: str, codigo_hash: str) -> dict[str, Any] | None:
    return await _col(db).find_one({"ruc": ruc, "codigo_hash": codigo_hash})


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count
