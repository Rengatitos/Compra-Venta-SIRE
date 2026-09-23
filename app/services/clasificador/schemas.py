from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class EconomicActivity(FlexibleModel):
    tipo: str | None = None
    ciiu_v4: str | None = None
    ciiu: str | None = None
    descripcion: str | None = None


class CompanyContext(FlexibleModel):
    ruc: str
    razon_social: str | None = None
    actividades_economicas: list[EconomicActivity] = Field(default_factory=list)
    comprobantes_autorizados: list[str] = Field(default_factory=list)
    comprobantes_autorizados_impresion: list[str] = Field(default_factory=list)
    sistema_emision_electronica: list[dict[str, Any]] = Field(default_factory=list)
    emisor_electronico_desde: str | None = None
    comprobantes_electronicos: list[str] = Field(default_factory=list)

    def normalized_activities(self) -> list[EconomicActivity]:
        for activity in self.actividades_economicas:
            if not activity.ciiu_v4 and activity.ciiu:
                activity.ciiu_v4 = activity.ciiu
        return self.actividades_economicas


class PeriodContext(FlexibleModel):
    periodo: str | None = None
    libro: str | None = None
    observaciones: list[str] = Field(default_factory=list)


class Counterparty(FlexibleModel):
    tipo_documento: str | None = None
    numero_documento: str | None = None
    razon_social: str | None = None
    actividades_economicas: list[EconomicActivity] = Field(default_factory=list)
    comprobantes_autorizados: list[str] = Field(default_factory=list)
    sistema_emision_electronica: list[dict[str, Any]] = Field(default_factory=list)


class VoucherType(FlexibleModel):
    codigo: str
    descripcion: str | None = None


class Amounts(FlexibleModel):
    base_imponible: float | None = None
    igv: float | None = None
    exonerado: float | None = None
    inafecto: float | None = None
    no_gravado: float | None = None
    icbper: float | None = None
    otros_tributos: float | None = None
    total: float | None = None


class Voucher(FlexibleModel):
    libro: str
    tipo_cp: VoucherType
    serie: str | None = None
    numero: str | None = None
    fecha_emision: str | None = None
    fecha_vencimiento: str | None = None
    contraparte: Counterparty | None = None
    moneda: str | None = None
    origen: str | None = None
    importes: Amounts | None = None


class VoucherItem(FlexibleModel):
    descripcion: str
    codigo: str | None = None
    cantidad: float | None = None
    unidad_medida: str | None = None
    valor_unitario: float | None = None
    precio_unitario: float | None = None
    valor_venta: float | None = None


class ClassifyRequest(FlexibleModel):
    empresa: CompanyContext | None = None
    empresa_ruc: str | None = None
    contexto_periodo: PeriodContext | None = None
    comprobante: Voucher
    items: list[VoucherItem] = Field(default_factory=list)
    contraparte_ruc: str | None = None


class AccountChoice(BaseModel):
    codigo: str
    descripcion: str | None = None


class ClassificationCore(BaseModel):
    clasificacion: str
    subtipo: str
    cuenta_base_imponible: AccountChoice | None = None
    cuenta_total: AccountChoice | None = None
    centro_costos: str | None = None
    condicion_igv: str
    confianza: float = Field(ge=0.0, le=1.0)
    razon: str


class RAGEvidence(BaseModel):
    source: str
    score: float
    semantic_score: float
    lexical_score: float
    metadata_score: float
    source_weight: float
    snippet: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClassificationResponse(ClassificationCore):
    requiere_revision: bool
    confianza_rag: float
    evidencias_rag: list[RAGEvidence] = Field(default_factory=list)
    debug: dict[str, Any] | None = None


class OperationInterpretation(BaseModel):
    direccion: str
    naturaleza: str
    concepto: str
    tipo_operacion: str | None = None
    destino_probable: str | None = None
    actividad_empresa_relevante: EconomicActivity | None = None
    actividad_contraparte_relevante: EconomicActivity | None = None
    relacion_actividad_empresa: str | None = None
    relacion_actividad_proveedor: str | None = None
    relacion_actividad_contraparte: str | None = None
    ciiu_proveedor_relevante: str | None = None
    operacion_fuera_giro_probable: bool | None = None
    confianza_interpretacion: float = Field(ge=0.0, le=1.0)
    razon: str


class EconomicPurpose(BaseModel):
    area_funcional: Literal["ADMINISTRACION", "VENTAS", "PRODUCCION", "CDS", "OPERACION", "MERCADERIA", "ACTIVO", "COSTO_DIRECTO", "INDETERMINADO"]
    relacion_actividad_principal: str | None = None
    tratamiento_contable: str | None = None
    nivel_confianza: float = Field(ge=0.0, le=1.0)
    razon: str


class AccountCandidate(BaseModel):
    codigo: str
    descripcion: str | None = None
    score: float = 0.0
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    score_components: dict[str, float] = Field(default_factory=dict)


class ConfidenceComponents(BaseModel):
    interpretation: float = 0.0
    retrieval_quality: float = 0.0
    evidence_coherence: float = 0.0
    base_account_support: float = 0.0
    total_account_support: float = 0.0
    completeness: float = 0.0
    candidate_margin: float = 0.0


class RAGSearchRequest(FlexibleModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=10)
    facts: dict[str, Any] = Field(default_factory=dict)


class RAGSearchResponse(BaseModel):
    query: str
    confianza_rag: float
    results: list[RAGEvidence]


class IndexUpdateResponse(BaseModel):
    backend: str
    documents_total: int
    documents_updated: int
    documents_reused: int
    documents_removed: int
    chunks_total: int
    embeddings_recomputed: int


class ModelStatus(BaseModel):
    llm_provider: str = "google"
    llm_model: str
    gemini_configured: bool = False
    embedding_model: str
    llm_loaded: bool
    embedding_loaded: bool
    vector_backend: str | None = None
    chunks_indexed: int = 0
