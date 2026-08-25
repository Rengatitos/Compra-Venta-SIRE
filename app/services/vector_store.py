import logging

logger = logging.getLogger(__name__)


async def cargar_global_en_memoria(col) -> list[dict]:
    try:
        cursor = col.find({}, {"_id": 0, "texto": 1, "metadata": 1, "embedding": 1})
        docs = await cursor.to_list(length=None)
        logger.info("vector cargado en memoria: %s chunks", len(docs))
        return docs
    except Exception:
        logger.exception("Error cargando vector desde MongoDB")
        return []


async def guardar_chunks_usuario(
    user_id: str,
    filename: str,
    embeddings: list[dict],
    col,
) -> int:
    try:
        resultado = await col.delete_many(
            {"user_id": user_id, "metadata.documento": filename}
        )
        logger.info(
            "Chunks anteriores eliminados user_id=%s documento=%s anterior=%s",
            user_id,
            filename,
            resultado.deleted_count,
        )

        if not embeddings:
            return 0

        docs = [
            {
                "user_id": user_id,
                "texto": e["texto"],
                "metadata": e["metadata"],
                "embedding": e["embedding"],
            }
            for e in embeddings
        ]
        await col.insert_many(docs)
        logger.info(
            "Chunks insertados user_id=%s documento=%s total=%s",
            user_id,
            filename,
            len(docs),
        )
        return len(docs)
    except Exception:
        logger.exception(
            "Error guardando chunks usuario user_id=%s documento=%s", user_id, filename
        )
        raise


async def eliminar_documento_usuario(user_id: str, filename: str, col) -> int:
    try:
        resultado = await col.delete_many(
            {"user_id": user_id, "metadata.documento": filename}
        )
        logger.info(
            "Documento eliminado user_id=%s documento=%s chunks=%s",
            user_id,
            filename,
            resultado.deleted_count,
        )
        return resultado.deleted_count
    except Exception:
        logger.exception(
            "Error eliminando documento usuario user_id=%s documento=%s",
            user_id,
            filename,
        )
        raise


async def listar_documentos_usuario(user_id: str, col) -> list[str]:
    try:
        nombres = await col.distinct("metadata.documento", {"user_id": user_id})
        return sorted(nombres)
    except Exception:
        logger.exception("Error listando documentos usuario user_id=%s", user_id)
        return []


async def obtener_chunks_usuario(user_id: str, col) -> list[dict]:
    try:
        cursor = col.find(
            {"user_id": user_id},
            {"_id": 0, "texto": 1, "metadata": 1, "embedding": 1},
        )
        return await cursor.to_list(length=None)
    except Exception:
        logger.exception("Error obteniendo chunks usuario user_id=%s", user_id)
        return []


async def obtener_datos_simplificados(user_id: str, col) -> list[dict]:
    try:
        cursor = col.find(
            {"user_id": user_id},
            {"_id": 0, "texto": 1, "metadata": 1},
        )
        return await cursor.to_list(length=None)
    except Exception:
        logger.exception("Error obteniendo datos simplificados user_id=%s", user_id)
        return []
