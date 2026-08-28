
from pydantic import BaseModel, field_validator

from app.domain.periodo import MENSAJE_FORMATO, es_valido


class PeriodoBase(BaseModel):
    periodo: str

    @field_validator("periodo")
    @classmethod
    def validar_formato_periodo(cls, v: str) -> str:
        if not es_valido(v):
            raise ValueError(MENSAJE_FORMATO)
        return v


class PeriodoCreate(PeriodoBase):
    pass


class PeriodoUpdate(BaseModel):
    estado: str | None = None


class PeriodoResponse(PeriodoBase):
    estado: str

    model_config = {"from_attributes": True}
