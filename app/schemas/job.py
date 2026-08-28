from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProgresoResponse(BaseModel):
    actual: int = 0
    total: int = 0
    mensaje: str = ""
    porcentaje: float = 0.0


class JobResponse(BaseModel):
    job_id: str
    tipo: str
    estado: str
    ruc: str
    periodo: str
    libro: str | None = None
    progreso: ProgresoResponse
    resultado: dict[str, Any] | None = None
    error: str | None = None
    creado_en: datetime
    actualizado_en: datetime


class JobAceptado(BaseModel):
    job_id: str
    estado: str
    mensaje: str
