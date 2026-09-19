
from pydantic import BaseModel, Field, field_validator


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


class EmpresaResponse(EmpresaBase):
    id: str = Field(validation_alias="_id")
    nombre: str | None = None
    usuario: str
    fecha_creacion: str | None = None
    rubro: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v):
        return str(v)

    model_config = {"from_attributes": True, "populate_by_name": True}
