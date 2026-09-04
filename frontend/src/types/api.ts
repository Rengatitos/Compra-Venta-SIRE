/**
 * Espejo de `app/schemas/*.py`. Los nombres de campo son los que devuelve el
 * backend; no se renombra nada en el cliente para que buscar un campo en el
 * repo lleve directamente a su origen.
 */
import type {
  EstadoJob,
  EstadoPeriodo,
  EstadoProcesamiento,
  FuenteDato,
  Libro,
  ResultadoIA,
  TipoJob,
} from './domain';

/* — genéricos (app/schemas/generic.py) — */

export interface MessageResponse {
  mensaje: string;
}

/** `datos` es libre en el backend; cada llamada lo estrecha con su propio tipo. */
export interface StatusResponse<T = unknown> {
  estado: 'exito' | 'advertencia' | (string & {});
  mensaje: string | null;
  datos: T | null;
}

export interface FileListResponse {
  archivos: string[];
}

export interface DataResponse<T = unknown> {
  data: T;
}

export interface TemasResponse {
  temas: string[];
}

/* — auth y empresas (app/schemas/empresa.py) — */

export interface EmpresaLogin {
  ruc: string;
  usuario: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface EmpresaCreate {
  ruc: string;
  usuario: string;
  password: string;
  sunat_client_id?: string;
  sunat_client_secret?: string;
}

/**
 * Cambios parciales. Un `sunat_client_id`/`sunat_client_secret` vacío NO borra
 * el valor guardado: el backend lo lee como "no lo toques". Por eso el
 * formulario omite las claves en lugar de enviar cadenas vacías.
 */
export interface EmpresaUpdate {
  usuario?: string;
  password?: string;
  sunat_client_id?: string;
  sunat_client_secret?: string;
}

export interface EmpresaResponse {
  id: string;
  ruc: string;
  usuario: string;
  fecha_creacion: string | null;
  /** Deducido del CIIU dentro del token de SUNAT (`app/domain/rubro.py`). */
  rubro: string | null;
}

/* — periodos (app/schemas/periodo.py) — */

export interface PeriodoCreate {
  periodo: string;
}

export interface PeriodoUpdate {
  estado?: string;
}

export interface PeriodoResponse {
  periodo: string;
  estado: EstadoPeriodo;
}

/* — comprobantes (app/schemas/comprobante.py) — */

export interface LineaDetalle {
  producto: string | null;
  categoria_contable: string | null;
  cantidad: unknown;
  importe: unknown;
  razon: string | null;
}

export interface AnalisisIA {
  detalle: LineaDetalle[];
  cuenta_contable: string | null;
  centro_costos: string | null;
  condicion_igv: string | null;
  resultado: string | null;
  confianza: string | null;
  estado: string | null;
  documentos: boolean | null;
  descripcion: string | null;
  observaciones: string | null;
  rag: ClasificacionRAG | null;
}

export interface ClasificacionRAG {
  codigo_comprobante: string | null;
  codigo_identidad: string | null;
  cuenta_base: string | null;
  cuenta_total: string | null;
  glosa: string | null;
  respuesta_cuentas: string | null;
}

export interface PdfSunat {
  ruta: string;
  bytes: number;
  descargado_en: string | null;
}

export interface ComprobanteResponse {
  /** Identificador legible (`F001-123`). No es el `_id` de Mongo. */
  serie_numero: string;
  libro: Libro | (string & {});
  origen: string;

  tipo_cp: string;
  tipo_cp_descripcion: string;
  serie: string;
  numero: string;

  tipo_doc_identidad: string;
  documento_contraparte: string;
  razon_social: string;

  /** ISO `YYYY-MM-DD`, o `null` si SUNAT no la trajo. */
  fecha_emision: string | null;
  fecha_vencimiento: string | null;

  moneda: string;
  /** `0` cuando SUNAT no lo trajo (operacion en soles). */
  tipo_cambio: number;
  /**
   * Tasa de IGV en puntos porcentuales (18, 10.5 en la selva). `null` cuando
   * el comprobante no la trae — que no es lo mismo que una tasa de cero.
   */
  porcentaje_igv: number | null;

  /** Suma de los tres destinos de abajo. */
  base_imponible: number;
  igv: number;
  /**
   * El RCE reparte la base y el IGV segun el destino de la adquisicion:
   * gravadas (DG), gravadas y no gravadas (DGNG) y no gravadas (DNG). El
   * registro de compras los pide en columnas separadas. En ventas el RVIE no
   * hace ese reparto, asi que estos campos van en cero.
   */
  base_imponible_dg: number;
  igv_dg: number;
  base_imponible_dgng: number;
  igv_dgng: number;
  base_imponible_dng: number;
  igv_dng: number;
  exonerado: number;
  inafecto: number;
  /**
   * "Valor de las adquisiciones no gravadas" del RCE. SUNAT no separa
   * exonerado de inafecto en el registro de compras: los agrupa aquí.
   */
  no_gravado: number;
  isc: number;
  icbper: number;
  otros_tributos: number;
  total: number;

  estado_procesamiento: EstadoProcesamiento | (string & {});
  /** Salida del análisis IA. El backend la llama `analisis`, no `metadata_procesada`. */
  analisis: AnalisisIA | null;
  detalle_sunat: unknown[];
  /**
   * Respaldo descargado del portal SOL. `null` mientras no se haya corrido la
   * descarga de PDFs; `ruta` es relativa a `SUNAT_DATA_DIR` en el servidor.
   */
  pdf_sunat: PdfSunat | null;
  /** Referencia al comprobante que modifica una nota de crédito o débito. Sólo en ventas. */
  documentos_modificados: Record<string, unknown>[];
}

/** Único campo editable de un comprobante. */
export interface ComprobanteUpdate {
  descripcion: string;
}

/* — jobs (app/schemas/job.py) — */

export interface ProgresoResponse {
  actual: number;
  total: number;
  mensaje: string;
  porcentaje: number;
}

export interface JobResponse {
  job_id: string;
  tipo: TipoJob | (string & {});
  estado: EstadoJob;
  ruc: string;
  periodo: string;
  libro: Libro | null;
  progreso: ProgresoResponse;
  resultado: Record<string, unknown> | null;
  error: string | null;
  creado_en: string;
  actualizado_en: string;
}

export interface JobAceptado {
  job_id: string;
  estado: EstadoJob;
  mensaje: string;
}

/* — payloads de `StatusResponse.datos` — */

/** `POST …/propuesta`. `descartados` = filas que SUNAT trajo y el filtro rechazó. */
export interface ResultadoPropuesta {
  nuevos: number;
  actualizados: number;
  descartados: number;
}

/** `POST …/analisis`. */
export interface ResultadoAnalisis {
  total_encontradas: number;
  procesadas: number;
  errores: number;
  sin_datos: number;
  resultados: string[];
}

/** `POST …/referencias`. */
export interface ResultadoReferencia {
  chunks: number;
}

/* — plan de cuentas (app/schemas/plan_cuentas.py) — */

export interface CuentaResponse {
  cuenta: string;
  descripcion: string;
  tipo: string;
  analisis: string;
  centro_costos: string;
  /** 1 = elemento, 2 = cuenta, 3 = subcuenta y divisionarias. Dibuja la sangría. */
  nivel: number;
}

export interface PlanCuentasResponse {
  cuentas: CuentaResponse[];
  /** Total que casa con el filtro, no el de la página. */
  total: number;
}

export interface CargaResponse {
  mensaje: string;
  cuentas: number;
}

/* — PDFs (app/api/v1/routes/pdfs.py) — */

/** `resultado` del job `descarga_pdfs` cuando termina. */
export interface ResultadoDescargaPdfs {
  procesados: number;
  descargados: number;
  sin_pdf: number;
  /** Los que el tope de `SUNAT_MAX_PDFS` dejó para otra vuelta. */
  pendientes: number;
  bytes: number;
}

/* — auditoría (app/schemas/auditoria.py) — */

export interface FilaReporte {
  serie_numero: string;
  tipo_cp: string;
  tipo_cp_descripcion: string;
  fecha_emision: string | null;
  documento_contraparte: string;
  razon_social: string;
  moneda: string;

  /** Lo que declara el registro (propuesta del SIRE). */
  base_imponible: number;
  igv: number;
  total: number;

  /**
   * Suma de las líneas leídas del portal. `null` cuando no hay detalle
   * extraído, que no es lo mismo que un importe de cero.
   */
  importe_detalle: number | null;
  diferencia: number | null;
  lineas_detalle: number;
  detalle_sunat: unknown[];

  glosa: string;
  cuenta_base: string;
  cuenta_total: string;
  observaciones: string;

  fuentes: FuenteDato[];
  /** Ruta relativa dentro del almacén, o `null` si no se descargó. */
  pdf: string | null;
}

export interface ResumenReporte {
  comprobantes: number;
  con_pdf: number;
  con_detalle: number;
  con_glosa: number;
  /**
   * Se separan a propósito: «0 descuadrados» sobre 0 comparables no dice
   * nada, y presentarlo como si cuadrara todo sería mentir.
   */
  comparables: number;
  descuadrados: number;
  total_registro: number;
}

export interface ReporteResponse {
  periodo: string;
  libro: Libro | (string & {});
  filas: FilaReporte[];
  resumen: ResumenReporte;
  zip_disponible: boolean;
}

/* — analytics (app/services/analytics_service.py) — */

export interface AnalyticsSummary {
  total_comprobantes: number;
  /**
   * Moneda de `total_monto` y `total_igv`. Siempre `PEN`: los comprobantes en
   * moneda extranjera se convierten con su propio tipo de cambio antes de
   * sumarlos, porque el registro se lleva en moneda nacional.
   */
  moneda: string;
  total_monto: number;
  total_igv: number;
  /**
   * Comprobantes en moneda extranjera que no traían tipo de cambio. Se suman
   * por su valor nominal, así que los totales se quedan cortos: si esto no es
   * cero, hay que decirlo.
   */
  sin_tipo_cambio: number;
  procesadas: number;
  pendientes: number;
}

export interface ContraparteTop {
  name: string;
  total: number;
}

export interface ClasificacionIA {
  name: ResultadoIA | (string & {});
  value: number;
}

export interface ComprobantesPorDia {
  name: string;
  qty: number;
}

export interface DashboardData {
  summary: AnalyticsSummary;
  top_contrapartes: ContraparteTop[];
  ai_classification: ClasificacionIA[];
  comprobantes_por_dia: ComprobantesPorDia[];
  comprobantes: ComprobanteResponse[];
}
