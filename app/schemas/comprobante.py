from datetime import date
from typing import Any

from pydantic import BaseModel


class LineaDetalle(BaseModel):
    producto: str | None = None
    categoria_contable: str | None = None
    cantidad: Any | None = None
    importe: Any | None = None
    razon: str | None = None


class ClasificacionRAG(BaseModel):
    codigo_comprobante: str | None = None
    codigo_identidad: str | None = None
    cuenta_base: str | None = None
    cuenta_total: str | None = None
    glosa: str | None = None
    respuesta_cuentas: str | None = None


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
    rag: ClasificacionRAG | None = None


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
    tipo_cambio: float = 0.0
    # `None` cuando el comprobante no trae tasa: un 0.0 aquí se leería como
    # "tasa cero", que no es lo mismo que "SUNAT no la mandó".
    porcentaje_igv: float | None = None

    base_imponible: float = 0.0
    igv: float = 0.0
    # Desglose por destino de la base y el IGV. Los declara el modelo aunque
    # casi siempre sólo el primero tenga importe: sin ellos aquí, Pydantic los
    # descartaba de la respuesta y el registro de compras que ve el cliente no
    # cuadraba con el Excel, que sí los escribe en columnas separadas.
    base_imponible_dg: float = 0.0
    igv_dg: float = 0.0
    base_imponible_dgng: float = 0.0
    igv_dgng: float = 0.0
    base_imponible_dng: float = 0.0
    igv_dng: float = 0.0
    exonerado: float = 0.0
    inafecto: float = 0.0
    no_gravado: float = 0.0
    isc: float = 0.0
    icbper: float = 0.0
    otros_tributos: float = 0.0
    total: float = 0.0

    estado_procesamiento: str
    analisis: AnalisisIA | None = None
    detalle_sunat: list[Any] = []
    # Referencia al comprobante que modifica una nota de crédito o débito.
    # Sólo el RVIE la manda; en compras (RCE) queda siempre vacía.
    documentos_modificados: list[dict[str, Any]] = []

    model_config = {"from_attributes": True}


class ComprobanteUpdate(BaseModel):
    descripcion: str | None = None
