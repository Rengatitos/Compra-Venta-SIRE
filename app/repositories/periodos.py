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


async def existentes(
    db: AsyncIOMotorDatabase, empresa_id: str, periodos: list[str]
) -> set[str]:
    """Cuáles de `periodos` ya existen para la empresa."""
    if not periodos:
        return set()
    return set(
        await _col(db).distinct("periodo", {"empresa_id": empresa_id, "periodo": {"$in": periodos}})
    )


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


async def guardar_npds(db, empresa_id, periodo, npds, consultado_en):
    await _col(db).update_one(
        {"empresa_id": empresa_id, "periodo": periodo},
        {"$set": {"npds": npds, "npds_consultado_en": consultado_en}},
    )


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count


async def listar_por_empresas(
    db: AsyncIOMotorDatabase, empresa_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Los periodos de varias empresas en una sola consulta, del más reciente al
    más antiguo, agrupados por `empresa_id`."""
    if not empresa_ids:
        return {}
    cursor = _col(db).find(
        {"empresa_id": {"$in": empresa_ids}},
        {"empresa_id": 1, "periodo": 1, "estado": 1},
    ).sort("periodo", -1)
    agrupados: dict[str, list[dict[str, Any]]] = {}
    async for documento in cursor:
        agrupados.setdefault(documento["empresa_id"], []).append(
            {"periodo": documento["periodo"], "estado": documento.get("estado")}
        )
    return agrupados
