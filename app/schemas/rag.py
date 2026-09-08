from pydantic import BaseModel


class EstadoRag(BaseModel):
    """Filas por índice del RAG contable. Ver `ollama_rag.estado_indices`."""

    cuentas: int
    historicos: int
    reglas: int
    # `True` en cuanto hay cuentas indexadas: es lo único imprescindible para
    # que la clasificación pueda devolver una cuenta contable.
    listo: bool
