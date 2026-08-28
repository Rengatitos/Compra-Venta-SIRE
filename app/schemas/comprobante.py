from datetime import date
from typing import Any

from pydantic import BaseModel


class LineaDetalle(BaseModel):
    producto: str | None = None
    categoria_contable: str | None = None
    cantidad: Any | None = None
    importe: Any | None = None
    razon: str | None = None


class AnalisisIA(BaseModel):
    detalle: list[LineaDetalle] = []
    cuenta_contable: str | None = None
    centro_costos: str | None = None
    condicion_igv: str | None = None
    resultado: str | None = None
    confianza: str | None = None
    estado: str | None = None
    documentos: bool | None = None
    descripcion: str | None = None
    observaciones: str | None = None


class ComprobanteResponse(BaseModel):
    serie_numero: str
    libro: str
    origen: str

    tipo_cp: str
    tipo_cp_descripcion: str
    serie: str
    numero: str

    tipo_doc_identidad: str = ""
    documento_contraparte: str = ""
    razon_social: str = ""

    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None

    moneda: str = "PEN"
    base_imponible: float = 0.0
    igv: float = 0.0
    exonerado: float = 0.0
    inafecto: float = 0.0
    otros_tributos: float = 0.0
    total: float = 0.0

    estado_procesamiento: str
    analisis: AnalisisIA | None = None
    detalle_sunat: list[Any] = []

    model_config = {"from_attributes": True}


class ComprobanteUpdate(BaseModel):
    descripcion: str | None = None
