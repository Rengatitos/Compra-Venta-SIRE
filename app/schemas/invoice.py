from pydantic import BaseModel, Field
from typing import List, Optional, Any

class InvoiceDetailItem(BaseModel):
    producto: Optional[str] = None
    categoria_contable: Optional[str] = None
    cantidad: Optional[Any] = None
    importe: Optional[Any] = None
    razon: Optional[str] = None


class SunatInvoiceData(BaseModel):
    """Datos crudos sincronizados desde el SIRE/SUNAT."""
    id_referencia: str = Field(..., alias="_ID_REFERENCIA")
    ruc_emisor: Optional[str] = Field(None, alias="RUC_EMISOR")
    nombre_proveedor: Optional[str] = Field(None, alias="NOMBRE_PROVEEDOR")
    fecha_emision: Optional[str] = Field(None, alias="FECHA_EMISION")
    total: Optional[float] = Field(None, alias="TOTAL")
    estado: str = Field(..., alias="ESTADO")
    raw_data: Optional[str] = Field(None, alias="RAW_DATA")
    detalle_compras_sunat: Optional[List[Any]] = None


class AIAnalysisData(BaseModel):
    """Resultado del análisis/clasificación contable hecho por Gemini."""
    detalle: List[InvoiceDetailItem] = []
    cuenta_contable: Optional[str] = None
    centro_costos: Optional[str] = None
    condicion_igv: Optional[str] = None
    resultado: Optional[str] = None
    ia_confidence: Optional[str] = None
    ia_status: Optional[str] = None


class InvoiceWorkflowData(BaseModel):
    """Metadata de workflow/UI editable por el usuario, independiente del origen SUNAT o IA."""
    Documentos: Optional[bool] = None
    Descripcion: Optional[str] = None
    Observaciones: Optional[str] = None


class InvoiceResponse(SunatInvoiceData, AIAnalysisData, InvoiceWorkflowData):
    """Vista compuesta de una factura para la API. El JSON de salida no cambia:
    solo se separaron los campos en sub-modelos por responsabilidad (SUNAT / IA / workflow)."""

    model_config = {
        "populate_by_name": True,
        "from_attributes": True
    }
