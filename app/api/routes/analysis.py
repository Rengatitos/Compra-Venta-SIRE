import asyncio
import logging
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import require_same_user
from app.db.database import get_db, get_vector_users_col
from app.services import analisis_ia, vector_store
from app.schemas.generic import StatusResponse


limiter = Limiter(key_func=get_remote_address)
router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=StatusResponse)
@limiter.limit("5/minute")
async def ejecutar_analisis(
    request: Request,
    user_id: str,
    periodo: str,
    archivos: List[UploadFile] = File(default=[]),
    rubro: str = "General",
    db=Depends(get_db),
    user=Depends(require_same_user),
):
    try:
        logger.info(
            "POST analisis IA user_id=%s periodo=%s auth_user_id=%s rubro=%s archivos=%s",
            user_id,
            periodo,
            str(user.get("_id")),
            rubro,
            len(archivos),
        )

        vector_db_usuario = []

        for archivo in archivos:
            if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
                continue

            pdf_bytes = await archivo.read()
            chunks = await asyncio.to_thread(
                analisis_ia.extraer_chunks_pdf,
                pdf_bytes,
                archivo.filename,
            )
            if chunks:
                embeddings_chunks = await asyncio.to_thread(
                    analisis_ia.generar_embeddings_pdf,
                    chunks,
                )
                vector_db_usuario.extend(embeddings_chunks)

        if not vector_db_usuario:
            col = get_vector_users_col()
            vector_db_usuario = await vector_store.obtener_chunks_usuario(user_id, col)
            if vector_db_usuario:
                logger.info(
                    "Usando RAG user_id=%s chunks=%s",
                    user_id,
                    len(vector_db_usuario),
                )

        resultado = await analisis_ia.procesar_lote_extracciones(
            user_id,
            periodo,
            db,
            vector_db_usuario if vector_db_usuario else None,
            rubro=rubro,
        )
        return {
            "estado": "exito",
            "mensaje": "Analisis completado",
            "datos": resultado,
        }
    except Exception as e:
        logger.exception("Error ejecutando analisis IA user_id=%s periodo=%s", user_id, periodo)
        raise HTTPException(status_code=500, detail=str(e))
