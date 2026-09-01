from __future__ import annotations

import logging
from typing import Any

import fitz
import numpy as np

from app.domain.comprobante import EstadoProcesamiento
from app.services import ollama_rag

logger = logging.getLogger(__name__)
vector_db: list[dict[str, Any]] = []


async def cargar_vector(db) -> None:
    from app.repositories import vectores

    global vector_db
    vector_db = await vectores.cargar_global(db)
    logger.info("Vector global Ollama listo con %s chunks", len(vector_db))


def extraer_chunks_pdf(pdf_bytes: bytes, filename: str, max_chars: int = 1500) -> list[dict]:
    try:
        documento = fitz.open(stream=pdf_bytes, filetype="pdf")
        chunks = []
        for pagina_numero, pagina in enumerate(documento, start=1):
            texto = pagina.get_text("text").strip()
            for inicio in range(0, len(texto), max_chars):
                fragmento = texto[inicio : inicio + max_chars].strip()
                if fragmento:
                    chunks.append(
                        {
                            "texto": fragmento,
                            "metadata": {"documento": filename, "pagina": pagina_numero},
                        }
                    )
        documento.close()
        return chunks
    except Exception:
        logger.exception("Error extrayendo texto de %s", filename)
        return []


def generar_embeddings_pdf(chunks: list[dict]) -> list[dict]:
    if not chunks:
        return []
    vectores = ollama_rag.embed_documents([chunk["texto"] for chunk in chunks])
    return [
        {"texto": c["texto"], "metadata": c["metadata"], "embedding": v}
        for c, v in zip(chunks, vectores, strict=True)
    ]


def buscar_contexto(texto: str, vector_db_usuario=None, top_k: int = 20) -> str:
    candidatos = [*(vector_db or []), *(vector_db_usuario or [])]
    if not candidatos:
        return "No hay referencias PDF disponibles."
    pregunta = np.asarray(ollama_rag.embed_query(texto))
    resultados = []
    for item in candidatos:
        vector = np.asarray(item.get("embedding") or [])
        if vector.size != pregunta.size or not vector.size:
            continue
        divisor = np.linalg.norm(pregunta) * np.linalg.norm(vector)
        resultados.append((float(np.dot(pregunta, vector) / divisor) if divisor else 0, item))
    resultados.sort(key=lambda par: par[0], reverse=True)
    return "\n".join(
        f"[{i.get('metadata', {}).get('documento', '')}] {i.get('texto', '')}"
        for _, i in resultados[:top_k]
    )


async def procesar_lote(
    db, empresa: dict, periodo: str, vector_db_usuario=None, rubro: str = "General"
) -> dict:
    from app.repositories import comprobantes as repo_comprobantes

    pendientes = await repo_comprobantes.listar_pendientes_analisis(
        db, str(empresa["_id"]), periodo
    )
    resultados: list[str] = []
    for documento in pendientes:
        documento_id = documento["_id"]
        if not (documento.get("extra") or {}).get("raw_sire") and not documento.get(
            "detalle_sunat"
        ):
            await repo_comprobantes.actualizar_estado(
                db, documento_id, EstadoProcesamiento.SIN_DATOS
            )
            resultados.append("sin_datos")
            continue
        try:
            clasificacion = await ollama_rag.clasificar(db, documento, empresa)
            metadata = dict(documento.get("metadata_procesada") or {})
            metadata.update(ollama_rag.a_formato_legacy(clasificacion, documento))
            await repo_comprobantes.guardar_analisis(
                db,
                documento_id,
                metadata,
                EstadoProcesamiento.ANALIZADO,
            )
            resultados.append("exito")
        except Exception:
            logger.exception(
                "Error analizando con Ollama comprobante=%s", documento.get("serie_numero")
            )
            await repo_comprobantes.actualizar_estado(
                db, documento_id, EstadoProcesamiento.ERROR_ANALISIS
            )
            resultados.append("error")
    return {
        "total_encontradas": len(pendientes),
        "procesadas": resultados.count("exito"),
        "errores": resultados.count("error"),
        "sin_datos": resultados.count("sin_datos"),
        "resultados": resultados,
    }
