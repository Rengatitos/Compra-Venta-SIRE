import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.auth import require_same_user, verify_user
from app.db.database import get_vector_users_col
from app.services import analisis_ia, vector_store
from app.schemas.generic import StatusResponse, FileListResponse, DataResponse, TemasResponse


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/files/{user_id}", response_model=FileListResponse)
async def listar_archivos(user_id: str, user=Depends(require_same_user)):
    """Lista los PDFs indexados por el usuario."""
    col = get_vector_users_col()
    archivos = await vector_store.listar_documentos_usuario(user_id, col)
    return {"archivos": archivos}


@router.post("/upload/{user_id}", response_model=StatusResponse)
async def subir_referencia(
    user_id: str,
    archivo: UploadFile = File(...),
    user=Depends(require_same_user),
):
    """Sube un PDF, extrae chunks, genera embeddings y los guarda en vector_users."""
    if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")

    try:
        content = await archivo.read()

        logger.info("Indexando referencia PDF user_id=%s archivo=%s", user_id, archivo.filename)
        chunks = await asyncio.to_thread(
            analisis_ia.extraer_chunks_pdf,
            content,
            archivo.filename,
        )

        if not chunks:
            return {
                "estado": "advertencia",
                "mensaje": "Archivo recibido pero no se pudo extraer texto.",
            }

        new_embeddings = await asyncio.to_thread(
            analisis_ia.generar_embeddings_pdf,
            chunks,
        )

        col = get_vector_users_col()
        total = await vector_store.guardar_chunks_usuario(
            user_id, archivo.filename, new_embeddings, col
        )

        return {
            "estado": "exito",
            "mensaje": f"Archivo '{archivo.filename}' indexado correctamente.",
            "chunks": total,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Error procesando referencia PDF user_id=%s archivo=%s",
            user_id,
            archivo.filename,
        )
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo: {str(e)}")


@router.delete("/files/{user_id}/{filename}", response_model=StatusResponse)
async def eliminar_referencia(
    user_id: str,
    filename: str,
    user=Depends(require_same_user),
):
    """Elimina todos los chunks de un documento indexado del usuario."""
    col = get_vector_users_col()
    eliminados = await vector_store.eliminar_documento_usuario(user_id, filename, col)
    if eliminados == 0:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return {"estado": "exito", "chunks_eliminados": eliminados}


@router.get("/data/{user_id}", response_model=DataResponse)
async def obtener_datos_vectoriales(user_id: str, user=Depends(require_same_user)):
    """Devuelve los textos indexados para el usuario."""
    col = get_vector_users_col()
    datos = await vector_store.obtener_datos_simplificados(user_id, col)
    return {"data": datos}


@router.get("/base-topics", response_model=TemasResponse)
async def obtener_temas_base(user=Depends(verify_user)):
    """Lista los documentos de la base global PCGE."""
    temas = set()
    for item in analisis_ia.vector_db:
        doc_name = item.get("metadata", {}).get("documento")
        if doc_name:
            temas.add(doc_name.strip())

    if not temas and analisis_ia.vector_db:
        for item in analisis_ia.vector_db[:50]:
            texto = item.get("texto", "").strip()
            if texto:
                temas.add(texto.split("\n")[0][:100].strip())

    if not temas:
        return {"temas": ["Base de conocimientos estándar (PCGE)"]}

    return {"temas": sorted(temas)}
