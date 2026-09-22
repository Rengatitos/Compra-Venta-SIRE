from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.domain.captura.period import parse_period
from app.services.captura.twilio import normalize_phone


class PhoneInput(BaseModel):
    phone: str
    active: bool = True

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return normalize_phone(value)


class PeriodInput(BaseModel):
    accounting_period: str

    @field_validator("accounting_period")
    @classmethod
    def period_format(cls, value):
        period = parse_period(value)
        if not period:
            raise ValueError("Periodo inválido; usa YYYYMM")
        return period


class DocumentUpdate(BaseModel):
    revision: int = Field(ge=0)
    fields: dict[str, str | None] = Field(default_factory=dict, max_length=60)
    document_type: str | None = Field(default=None, max_length=40)
    document_date: date | None = None
    review_note: str | None = Field(default=None, max_length=500)

    @field_validator("fields")
    @classmethod
    def field_lengths(cls, values):
        if any(value is not None and len(value) > 1000 for value in values.values()):
            raise ValueError("Campo demasiado largo")
        return values


class ActionInput(BaseModel):
    revision: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=500)


class MovePeriodInput(PeriodInput, ActionInput):
    pass
