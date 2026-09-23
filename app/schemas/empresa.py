
from pydantic import BaseModel, Field, field_validator

from app.services.sunat.ficha_ruc import FichaRuc


class ActividadEconomica(BaseModel):
    """Actividad de la ficha RUC. La usa el clasificador contable como contexto."""

    tipo: str | None = None  # PRINCIPAL / SECUNDARIA
    ciiu: str
    descripcion: str | None = None

    @field_validator("ciiu")
    @classmethod
    def validar_ciiu(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("El CIIU debe ser numérico")
        return v


class EmpresaBase(BaseModel):
    ruc: str

    @field_validator("ruc")
    @classmethod
    def validar_ruc(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit() or len(v) != 11:
            raise ValueError("El RUC debe tener 11 dígitos")
        return v


class EmpresaCreate(EmpresaBase):
    usuario: str
    password: str
    nombre: str | None = None
    sunat_client_id: str | None = None
    sunat_client_secret: str | None = None


class EmpresaUpdate(BaseModel):
    nombre: str | None = None
    usuario: str | None = None
    password: str | None = None
    sunat_token: str | None = None
    sunat_client_id: str | None = None
    sunat_client_secret: str | None = None
    actividades_economicas: list[ActividadEconomica] | None = None


class EmpresaResponse(EmpresaBase):
    id: str = Field(validation_alias="_id")
    nombre: str | None = None
    usuario: str
    fecha_creacion: str | None = None
    rubro: str | None = None
    actividades_economicas: list[ActividadEconomica] = []
    # Última ficha RUC consultada en SUNAT (`POST /empresas/{ruc}/ficha-ruc`).
    ficha_ruc: FichaRuc | None = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v):
        return str(v)

    model_config = {"from_attributes": True, "populate_by_name": True}
