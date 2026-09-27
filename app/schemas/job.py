from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProgresoResponse(BaseModel):
    actual: int = 0
    total: int = 0
    mensaje: str = ""
    porcentaje: float = 0.0


class ErrorIntentoResponse(BaseModel):
    intento: int | None = None
    en: datetime | None = None
    error: str = ""


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
    # Cola durable: si lo ejecuta el worker, intentos y cuándo toca el próximo.
    gestionado: bool = False
    solicitud_id: str | None = None
    intentos: int = 0
    max_intentos: int = 1
    ultimo_intento_en: datetime | None = None
    siguiente_intento_en: datetime | None = None
    historial_errores: list[ErrorIntentoResponse] = []


class JobAceptado(BaseModel):
    job_id: str
    estado: str
    mensaje: str
