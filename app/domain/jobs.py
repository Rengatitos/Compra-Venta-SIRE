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
    DESCARGA_PDFS = "descarga_pdfs"
    DETRACCIONES = "detracciones"
    CLASIFICACION_CUENTAS = "clasificacion_cuentas"
    # Propuesta SIRE de un libro. La que se pide a mano desde el periodo sigue
    # siendo síncrona y solo deja el job como historial; la de una solicitud
    # masiva pasa por la cola.
    SINCRONIZACION_SIRE = "sincronizacion_sire"
    # Pasos automáticos tras dar de alta una empresa (token, CIIU, rubro).
    ALTA_EMPRESA = "alta_empresa"
    # Credenciales del API SUNAT de una empresa que no las tiene.
    CREDENCIALES_SUNAT = "credenciales_sunat"
    # Excel y comprobantes de una solicitud, organizados en un ZIP.
    EMPAQUETADO = "empaquetado"
    # Correo final de una solicitud.
    ENVIO_CORREO = "envio_correo"


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

    # Cola durable (`app.services.cola`). Un job `gestionado` lo ejecuta el
    # worker a partir de lo guardado aquí, así que sobrevive a que se cierre la
    # página y a un reinicio. Los que no lo son (historial de una propuesta
    # síncrona, o los que dejó una versión anterior de la API) el worker no los
    # toca.
    gestionado: bool = False
    # Carril de exclusión: dos jobs del mismo carril no corren a la vez. El RUC
    # para lo que entra con la sesión SOL, que es única por usuario.
    cola: str | None = None
    parametros: dict[str, Any] = Field(default_factory=dict)
    solicitud_id: str | None = None

    intentos: int = 0
    max_intentos: int = 1
    ultimo_intento_en: datetime | None = None
    siguiente_intento_en: datetime | None = None
    latido_en: datetime | None = None
    historial_errores: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def terminado(self) -> bool:
        return self.estado in ESTADOS_TERMINALES
