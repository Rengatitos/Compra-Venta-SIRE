import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual, libro_valido, periodo_valido
from app.db.database import get_db
from app.domain import rubro as dominio_rubro
from app.domain.comprobante import Libro
from app.repositories import vectores as repo_vectores
from app.schemas.generic import StatusResponse
from app.services import analisis_ia

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post("", response_model=StatusResponse, summary="Analizar los comprobantes con IA")
@limiter.limit("5/minute")
async def ejecutar_analisis(
    request: Request,
    archivos: list[UploadFile] = File(default=[]),
    periodo: str = Depends(periodo_valido),
    libro: Libro = Depends(libro_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    empresa_id = str(empresa["_id"])

    rubro = dominio_rubro.desde_token_sunat(empresa.get("sunat_token", ""))

    try:
        contexto_usuario: list[dict] = []

        for archivo in archivos:
            if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
                continue
            contenido = await archivo.read()
            chunks = await asyncio.to_thread(
                analisis_ia.extraer_chunks_pdf, contenido, archivo.filename
            )
            if chunks:
                contexto_usuario.extend(
                    await asyncio.to_thread(analisis_ia.generar_embeddings_pdf, chunks)
                )

        # Sin PDFs en la petición se usa lo que la empresa ya tenga indexado.
        if not contexto_usuario:
            contexto_usuario = await repo_vectores.obtener_chunks(db, empresa_id)
            if contexto_usuario:
                logger.info(
                    "Usando RAG indexado empresa_id=%s chunks=%s",
                    empresa_id,
                    len(contexto_usuario),
                )

        resultado = await analisis_ia.procesar_lote(
            db,
            empresa,
            periodo,
            libro,
            contexto_usuario or None,
            rubro=rubro,
        )
        return {"estado": "exito", "mensaje": "Análisis completado", "datos": resultado}
    except Exception as exc:
        logger.exception(
            "Error ejecutando el análisis IA empresa_id=%s periodo=%s libro=%s",
            empresa_id,
            periodo,
            libro.value,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
