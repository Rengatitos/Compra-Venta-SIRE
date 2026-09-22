"""Contrato con sire-bot. Los nombres de campo son los de `sire-bot/docs/sire-contract.md`."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.comprobante import Libro
from app.domain.comprobante_externo import Fuente, TipoEvidencia

MONTO_RE = re.compile(r"^\d+\.\d{2}$")


def _monto(valor: object, campo: str) -> Decimal | None:
    # Los montos viajan como texto a propósito: un float de JSON ya habría
    # perdido precisión antes de llegar aquí.
    if valor is None:
        return None
    if not isinstance(valor, str) or not MONTO_RE.match(valor):
        raise ValueError(f'{campo} debe ser un monto en texto con dos decimales, p. ej. "1234.50"')
    return Decimal(valor)


class ContraparteExterna(BaseModel):
    tipo_doc_identidad: str = ""
    documento: str = ""
    nombre: str = ""


class ImagenExterna(BaseModel):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime: str
    bytes: int = Field(ge=0)
    # La foto ya procesada por el bot (≤1600 px). Opcional: si el bot la purgó
    # antes de un reenvío, llegan solo los metadatos.
    contenido_base64: str | None = None


class ComprobanteExternoCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id_externo: str = Field(min_length=1, max_length=64)
    libro: Libro
    fuente: Fuente
    tipo_evidencia: TipoEvidencia
    tipo_cp: str = Field(pattern=r"^\d{2}$")
    serie: str = ""
    numero: str = ""
    nro_operacion: str | None = None
    fecha_operacion: date
    hora_operacion: str | None = None
    moneda: Literal["PEN", "USD"]
    total: Decimal
    base_imponible: Decimal | None = None
    igv: Decimal | None = None
    contraparte: ContraparteExterna = Field(default_factory=ContraparteExterna)
    descripcion: str = ""
    confianza: float = Field(ge=0, le=1)
    campos_dudosos: list[str] = Field(default_factory=list)
    imagen: ImagenExterna
    dispositivo_id: str = Field(min_length=1)
    enviado_en: datetime

    @field_validator("total", mode="before")
    @classmethod
    def _total(cls, v: object) -> Decimal:
        monto = _monto(v, "total")
        if monto is None:
            raise ValueError("total es obligatorio")
        return monto

    @field_validator("base_imponible", "igv", mode="before")
    @classmethod
    def _opcionales(cls, v: object, info) -> Decimal | None:
        return _monto(v, info.field_name)

    @model_validator(mode="after")
    def _reglas(self) -> ComprobanteExternoCreate:
        if self.tipo_evidencia == TipoEvidencia.VOUCHER:
            if not (self.nro_operacion or "").strip():
                raise ValueError("un voucher requiere nro_operacion")
            if self.tipo_cp != "00":
                raise ValueError('un voucher debe tener tipo_cp "00"')
        else:
            if not self.serie.strip() or not self.numero.strip():
                raise ValueError("un comprobante requiere serie y numero")
        return self


class ComprobanteExternoRecibido(BaseModel):
    id: str
    ruc: str
    periodo: str
    estado: str
    creado_en: str


class ComprobanteExternoResponse(ComprobanteExternoRecibido):
    id_externo: str
    libro: str
    fuente: str
    tipo_evidencia: str
    tipo_cp: str
    tipo_cp_descripcion: str
    serie: str
    numero: str
    nro_operacion: str | None
    fecha_operacion: str | None
    hora_operacion: str | None
    moneda: str
    total: str
    base_imponible: str | None
    igv: str | None
    contraparte: ContraparteExterna
    descripcion: str
    confianza: float | None
    campos_dudosos: list[str]
    dispositivo_id: str
    enviado_en: str | None
    tiene_imagen: bool


class ListaComprobantesExternos(BaseModel):
    items: list[ComprobanteExternoResponse]
    total: int
    periodos: list[str]


class CodigoVinculacionResponse(BaseModel):
    codigo: str
    expira_en: str


class CanjeRequest(BaseModel):
    codigo: str
    dispositivo_id: str = Field(min_length=1, max_length=200)


class EmpresaVinculada(BaseModel):
    ruc: str
    nombre: str


class CanjeResponse(BaseModel):
    empresa: EmpresaVinculada
