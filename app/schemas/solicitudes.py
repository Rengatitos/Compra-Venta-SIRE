from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.generic import FechaUtc


class SolicitudCreate(BaseModel):
    """Qué procesar: empresas por RUC (o `"todas"`) y periodos AAAAMM (o
    `"todos"`, que son los registrados de cada empresa)."""

    empresas: list[str] | Literal["todas"] = Field(min_length=1)
    periodos: list[str] | Literal["todos"] = Field(min_length=1)
    clasificar: bool = True


class PasoResponse(BaseModel):
    paso: str
    estado: str
    job_id: str | None = None
    nota: str | None = None
    # Estado vivo del trabajo que ejecuta el paso.
    job_estado: str | None = None
    intentos: int | None = None
    max_intentos: int | None = None
    siguiente_intento_en: FechaUtc | None = None
    mensaje: str | None = None
    error: str | None = None


class ItemResponse(BaseModel):
    ruc: str
    nombre: str | None = None
    periodo: str
    estado: str
    observaciones: list[str] = []
    pasos: list[PasoResponse]


class ZipResponse(BaseModel):
    archivo: str
    bytes: int
    generado_en: FechaUtc | None = None


class EmpresaEnvio(BaseModel):
    ruc: str
    nombre: str | None = None


class EnvioResponse(BaseModel):
    correo: str
    empresas: list[EmpresaEnvio] = []
    periodos: list[str] = []
    estado: str
    modo: str | None = None
    intentos: int | None = 0
    error: str | None = None
    creado_en: FechaUtc | None = None
    enviado_en: FechaUtc | None = None


class EnvioListado(EnvioResponse):
    solicitud_id: str
    solicitud_creada_en: FechaUtc | None = None


class ProgresoSolicitud(BaseModel):
    actual: int
    total: int


class SolicitudResponse(BaseModel):
    id: str
    creado_por: str
    creado_en: FechaUtc
    terminado_en: FechaUtc | None = None
    estado: str
    clasificar: bool
    error: str | None = None
    progreso: ProgresoSolicitud
    items: list[ItemResponse]
    zip: ZipResponse | None = None
    envios: list[EnvioResponse] = []
