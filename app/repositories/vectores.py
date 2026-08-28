from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories._mongo import NOMBRE_COL_VECTOR_GLOBAL, NOMBRE_COL_VECTOR_USUARIOS

logger = logging.getLogger(__name__)

_PROYECCION = {"_id": 0, "texto": 1, "metadata": 1, "embedding": 1}


def _global(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_VECTOR_GLOBAL]


def _usuarios(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_VECTOR_USUARIOS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _global(db).create_index([("metadata.documento", 1)])
    await _usuarios(db).create_index([("empresa_id", 1), ("metadata.documento", 1)])


async def cargar_global(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    try:
        docs = await _global(db).find({}, _PROYECCION).to_list(length=None)
        logger.info("Vector global cargado en memoria: %s chunks", len(docs))
        return docs
    except Exception:
        logger.exception("Error cargando el vector global desde MongoDB")
        return []


async def guardar_chunks(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    filename: str,
    embeddings: list[dict[str, Any]],
) -> int:
    filtro = {"empresa_id": empresa_id, "metadata.documento": filename}
    anteriores = await _usuarios(db).delete_many(filtro)
    logger.info(
        "Chunks anteriores eliminados empresa_id=%s documento=%s total=%s",
        empresa_id,
        filename,
        anteriores.deleted_count,
    )

    if not embeddings:
        return 0

    docs = [
        {
            "empresa_id": empresa_id,
            "texto": e["texto"],
            "metadata": e["metadata"],
            "embedding": e["embedding"],
        }
        for e in embeddings
    ]
    await _usuarios(db).insert_many(docs)
    logger.info(
        "Chunks insertados empresa_id=%s documento=%s total=%s",
        empresa_id,
        filename,
        len(docs),
    )
    return len(docs)


async def eliminar_documento(
    db: AsyncIOMotorDatabase, empresa_id: str, filename: str
) -> int:
    resultado = await _usuarios(db).delete_many(
        {"empresa_id": empresa_id, "metadata.documento": filename}
    )
    return resultado.deleted_count


async def listar_documentos(db: AsyncIOMotorDatabase, empresa_id: str) -> list[str]:
    nombres = await _usuarios(db).distinct("metadata.documento", {"empresa_id": empresa_id})
    return sorted(nombres)


async def obtener_chunks(db: AsyncIOMotorDatabase, empresa_id: str) -> list[dict[str, Any]]:
    return await _usuarios(db).find({"empresa_id": empresa_id}, _PROYECCION).to_list(length=None)


async def obtener_datos_simplificados(
    db: AsyncIOMotorDatabase, empresa_id: str
) -> list[dict[str, Any]]:
    proyeccion = {"_id": 0, "texto": 1, "metadata": 1}
    return await _usuarios(db).find({"empresa_id": empresa_id}, proyeccion).to_list(length=None)


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _usuarios(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count
