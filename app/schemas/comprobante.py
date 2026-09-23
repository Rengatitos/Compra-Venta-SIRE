from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class PdfSunat(BaseModel):
    """Respaldo del comprobante descargado del portal SOL."""

    # Relativa al almacén (`SUNAT_DATA_DIR`), nunca absoluta: mover el
    # volumen no debe invalidar el puntero.
    ruta: str
    bytes: int = 0
    descargado_en: datetime | None = None


class CuentaClasificada(BaseModel):
    codigo: str
    descripcion: str | None = None


class ClasificacionContable(BaseModel):
    """Resultado del clasificador contable (`app/services/clasificacion_service.py`)."""

    cuenta_base: CuentaClasificada | None = None
    cuenta_total: CuentaClasificada | None = None
    clasificacion: str = ""
    subtipo: str = ""
    condicion_igv: str = ""
    centro_costos: str | None = None
    confianza: float = 0.0
    confianza_rag: float = 0.0
    # Con `True` la cuenta base no pasa al Excel: la confianza no llega al
    # umbral, falta alguna cuenta o hubo candidatos ambiguos.
    requiere_revision: bool = True
    razon: str = ""
    modelo: str = ""
    clasificado_en: datetime | None = None
    # `ia` (la clasificó Gemini) o `memoria` (reutilizada de una clasificación
    # frecuente). `memoria_id` apunta a esa clasificación frecuente.
    origen: str = "ia"
    memoria_id: str | None = None
    # Partes del motivo (`razon` es su texto compuesto): el camino de cada cuenta
    # en el plan de cuentas, el porqué que dio la IA y, si se reutilizó, cómo.
    jerarquia_base: list[CuentaClasificada] = []
    jerarquia_total: list[CuentaClasificada] = []
    motivo_ia: str = ""
    reutilizado: str | None = None


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
    analisis: None = None
    glosa: str = ""
    observacion: str = ""
    # `con_glosa`, `sin_glosa`, `en_evaluacion` o `pendiente`
    # (`app/services/glosa.py`). Depende del tipo de comprobante y de si ya se
    # consultó el portal; "pendiente" es un tipo consultable aún sin consultar.
    estado_glosa: str = "pendiente"
    # Recuadro «LEYENDA» del popup de SOL. Cuando los ítems no traen
    # descripción, la glosa sale de aquí.
    leyenda_sunat: list[str] = []
    detalle_sunat: list[Any] = []
    # True cuando la propuesta SUNAT contiene indDetraccion="D".
    detraccion: bool = False
    detracciones: list[dict[str, Any]] = []
    detracciones_consultado_en: str | None = None
    # `None` mientras no se haya corrido la descarga de PDFs. La pantalla de
    # auditoría lo usa para decir qué comprobantes siguen sin respaldo.
    pdf_sunat: PdfSunat | None = None
    # Referencia al comprobante que modifica una nota de crédito o débito.
    # Sólo el RVIE la manda; en compras (RCE) queda siempre vacía.
    documentos_modificados: list[dict[str, Any]] = []
    # `None` mientras no se haya clasificado.
    clasificacion_contable: ClasificacionContable | None = None

    model_config = {"from_attributes": True}


class ConteoEstadoGlosa(BaseModel):
    con_glosa: int = 0
    sin_glosa: int = 0
    en_evaluacion: int = 0
    pendiente: int = 0


class CoberturaSunat(BaseModel):
    """Cobertura de todo el libro en el periodo, independiente de la paginación."""

    total: int = 0
    con_detalle: int = 0
    con_pdf: int = 0
    estado_glosa: ConteoEstadoGlosa = ConteoEstadoGlosa()


class ComprobanteUpdate(BaseModel):
    razon_social: str | None = None
    documento_contraparte: str | None = None
    descripcion: str | None = None
