from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.comprobante import Libro


class EstadoJob(str, Enum):
    PENDIENTE = "pendiente"
    EN_PROGRESO = "en_progreso"
    COMPLETADO = "completado"
    FALLIDO = "fallido"


ESTADOS_TERMINALES = frozenset({EstadoJob.COMPLETADO, EstadoJob.FALLIDO})


class TipoJob(str, Enum):
    EXTRACCION_DETALLES = "extraccion_detalles"


class Progreso(BaseModel):
    actual: int = 0
    total: int = 0
    mensaje: str = ""

    @property
    def porcentaje(self) -> float:
        if self.total <= 0:
            return 0.0
        return round(min(self.actual / self.total, 1.0) * 100, 2)


def nuevo_job_id() -> str:
    return uuid4().hex


def _ahora() -> datetime:
    return datetime.now(UTC)


class Job(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    job_id: str = Field(default_factory=nuevo_job_id)
    tipo: TipoJob
    estado: EstadoJob = EstadoJob.PENDIENTE

    ruc: str
    periodo: str
    libro: Libro | None = None

    progreso: Progreso = Field(default_factory=Progreso)
    resultado: dict[str, Any] | None = None
    error: str | None = None

    creado_en: datetime = Field(default_factory=_ahora)
    actualizado_en: datetime = Field(default_factory=_ahora)

    @property
    def terminado(self) -> bool:
        return self.estado in ESTADOS_TERMINALES
