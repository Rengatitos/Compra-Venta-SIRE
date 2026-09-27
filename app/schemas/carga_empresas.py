from pydantic import BaseModel, Field, field_validator

from app.schemas.generic import FechaUtc


class FilaCargaResponse(BaseModel):
    fila: int
    ruc: str
    razon_social: str
    usuario: str
    estado: str
    motivos: list[str] = []
    empresa_id: str | None = None
    fecha_registro: FechaUtc | None = None


class ProgresoCarga(BaseModel):
    actual: int = 0
    total: int = 0
    mensaje: str = ""


class CargaResumen(BaseModel):
    id: str = Field(validation_alias="_id")
    modalidad: str
    archivo: str | None = None
    registrado_por: str
    estado: str
    progreso: ProgresoCarga
    creado_en: FechaUtc
    terminado_en: FechaUtc | None = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v):
        return str(v)

    model_config = {"populate_by_name": True}


class CargaResponse(CargaResumen):
    filas: list[FilaCargaResponse] = []


class CargaAceptada(BaseModel):
    carga_id: str
