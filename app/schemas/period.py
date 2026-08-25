import re
from pydantic import BaseModel, field_validator
from typing import Optional

_PERIODO_RE = re.compile(r"^20\d{2}(0[1-9]|1[0-2])$")


class PeriodBase(BaseModel):
    periodo: str

    @field_validator("periodo")
    @classmethod
    def validar_formato_periodo(cls, v: str) -> str:
        if not _PERIODO_RE.match(v):
            raise ValueError("El periodo debe tener el formato YYYYMM")
        return v


class PeriodCreate(PeriodBase):
    pass


class PeriodUpdate(BaseModel):
    estado: Optional[str] = None


class PeriodResponse(PeriodBase):
    estado: str

    class Config:
        from_attributes = True
