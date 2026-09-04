from datetime import date
from typing import Any

from pydantic import BaseModel


class FilaReporte(BaseModel):
    serie_numero: str
    tipo_cp: str
    tipo_cp_descripcion: str
    fecha_emision: date | None
    documento_contraparte: str
    razon_social: str
    moneda: str

    # Lo que declara el registro (propuesta del SIRE).
    base_imponible: float
    igv: float
    total: float

    # Lo que se pudo leer del comprobante en el portal. `None` cuando no hay
    # detalle extraído: no es lo mismo que un importe de cero.
    importe_detalle: float | None
    diferencia: float | None
    lineas_detalle: int
    detalle_sunat: list[Any]

    glosa: str
    cuenta_base: str
    cuenta_total: str
    observaciones: str

    # De dónde salió cada dato. Es lo que el auditor necesita para rastrear.
    fuentes: list[str]
    # Ruta relativa dentro del almacén, o `None` si no se descargó.
    pdf: str | None


class ResumenReporte(BaseModel):
    comprobantes: int
    con_pdf: int
    con_detalle: int
    con_glosa: int
    # Cuántos se pudieron comparar y cuántos de esos no cuadran. Se separan a
    # propósito: "0 descuadrados" sobre 0 comparables no dice nada.
    comparables: int
    descuadrados: int
    total_registro: float


class ReporteResponse(BaseModel):
    periodo: str
    libro: str
    filas: list[FilaReporte]
    resumen: ResumenReporte
    zip_disponible: bool
