import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.v1.deps import empresa_id
from app.core.auth import empresa_autenticada
from app.db.database import get_db
from app.repositories import vectores as repo_vectores
from app.schemas.generic import DataResponse, FileListResponse, StatusResponse, TemasResponse
from app.services import analisis_ia

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=FileListResponse, summary="Listar PDFs de referencia")
async def listar_referencias(empresa: str = Depends(empresa_id), db=Depends(get_db)):
    return {"archivos": await repo_vectores.listar_documentos(db, empresa)}


@router.post("", response_model=StatusResponse, summary="Subir un PDF de referencia")
async def subir_referencia(
    archivo: UploadFile = File(...),
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    if not archivo.filename or not archivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF")

    try:
        contenido = await archivo.read()
        logger.info(
            "Indexando referencia empresa_id=%s archivo=%s", empresa, archivo.filename
        )

        chunks = await asyncio.to_thread(
            analisis_ia.extraer_chunks_pdf, contenido, archivo.filename
        )
        if not chunks:
            return {
                "estado": "advertencia",
                "mensaje": "Archivo recibido pero no se pudo extraer texto",
            }

        embeddings = await asyncio.to_thread(analisis_ia.generar_embeddings_pdf, chunks)
        total = await repo_vectores.guardar_chunks(db, empresa, archivo.filename, embeddings)

        return {
            "estado": "exito",
            "mensaje": f"Archivo '{archivo.filename}' indexado correctamente",
            "datos": {"chunks": total},
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Error procesando referencia empresa_id=%s archivo=%s", empresa, archivo.filename
        )
        raise HTTPException(
            status_code=500, detail=f"Error al procesar el archivo: {exc}"
        ) from exc


@router.delete(
    "/{filename}", response_model=StatusResponse, summary="Eliminar un PDF de referencia"
)
async def eliminar_referencia(
    filename: str,
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    eliminados = await repo_vectores.eliminar_documento(db, empresa, filename)
    if eliminados == 0:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return {"estado": "exito", "datos": {"chunks_eliminados": eliminados}}


@router.get("/datos", response_model=DataResponse, summary="Datos vectoriales indexados")
async def obtener_datos_vectoriales(empresa: str = Depends(empresa_id), db=Depends(get_db)):
    return {"data": await repo_vectores.obtener_datos_simplificados(db, empresa)}


@router.get("/temas-base", response_model=TemasResponse, summary="Temas del vector global")
async def obtener_temas_base(_: dict = Depends(empresa_autenticada)):
    temas = {
        item.get("metadata", {}).get("documento", "").strip()
        for item in analisis_ia.vector_db
        if item.get("metadata", {}).get("documento")
    }
    if not temas:
        return {"temas": ["Base de conocimientos estándar (PCGE)"]}
    return {"temas": sorted(temas)}
