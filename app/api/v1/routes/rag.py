"""Estado del RAG contable.

Sirve para que la pantalla pueda explicar un dato ausente. Sin el índice de
cuentas, la clasificación termina «bien» pero con la cuenta en blanco, y el
usuario sólo ve un guion sin saber si es un fallo suyo, del modelo o de la
instalación.
"""

from fastapi import APIRouter, Depends

from app.core.auth import empresa_autenticada
from app.db.database import get_db
from app.schemas.rag import EstadoRag
from app.services import ollama_rag

router = APIRouter()


@router.get("/estado", response_model=EstadoRag, summary="Estado de los índices del RAG")
async def estado(
    _empresa: dict = Depends(empresa_autenticada),
    db=Depends(get_db),
):
    return await ollama_rag.estado_indices(db)
