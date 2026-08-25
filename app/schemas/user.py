from pydantic import BaseModel, Field, field_validator
from typing import Optional


class SolUserBase(BaseModel):
    ruc: str
    tenant_id: Optional[str] = None
    cliente_id: Optional[str] = None
    cuenta_id: Optional[str] = None


class SolUserCreate(SolUserBase):
    usuario: str
    password: str
    sunat_token: Optional[str] = None
    sunat_client_id: Optional[str] = None
    sunat_client_secret: Optional[str] = None

class SolUserUpdate(BaseModel):
    usuario: Optional[str] = None
    password: Optional[str] = None
    sunat_token: Optional[str] = None
    sunat_client_id: Optional[str] = None
    sunat_client_secret: Optional[str] = None
    tenant_id: Optional[str] = None
    cliente_id: Optional[str] = None
    cuenta_id: Optional[str] = None

class SolUserLogin(BaseModel):
    ruc: str
    usuario: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class SolUserResponse(SolUserBase):
    id: str = Field(validation_alias="_id")
    usuario: str
    fecha_creacion: Optional[str] = None
    rubro: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v):
        return str(v)

    model_config = {"from_attributes": True, "populate_by_name": True}


class SolUserCreateResponse(SolUserResponse):
    pass
