/**
 * Espejo de `app/schemas/*.py`. Los nombres de campo son los que devuelve el
 * backend; no se renombra nada en el cliente para que buscar un campo en el
 * repo lleve directamente a su origen.
 */
import type {
  EstadoCarga,
  EstadoEnvio,
  EstadoFilaCarga,
  EstadoGlosa,
  EstadoItemSolicitud,
  EstadoJob,
  EstadoPasoSolicitud,
  EstadoPeriodo,
  EstadoProcesamiento,
  EstadoSolicitud,
  FuenteDato,
  FuenteExterna,
  Libro,
  ModalidadCarga,
  PasoSolicitud,
  TipoJob,
} from './domain';

/* — genéricos (app/schemas/generic.py) — */

export interface MessageResponse {
  mensaje: string;
}

/** `datos` es libre en el backend; cada llamada lo estrecha con su propio tipo. */
/** Resultado de `POST /empresas/{ruc}/credenciales-sunat` (sin la clave). */
export interface CredencialesSunatResultado {
  origen: 'existente' | 'creada';
  aplicacion: string;
  /** Solo los primeros caracteres. */
  client_id: string;
  token_valido: boolean;
  mensaje: string;
}

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

/**
 * `credential` es el nombre con el que Google Identity Services entrega el ID
 * token en su callback; el backend lo copia para no renombrar nada por el medio.
 */
export interface LoginGoogle {
  credential: string;
}

export interface UsuarioResponse {
  email: string;
  nombre: string | null;
  foto: string | null;
  /** `admin` gestiona quién tiene acceso al panel; `usuario` no. */
  rol?: RolUsuario;
}

/** `app/domain/usuario.py::Rol`. */
export type RolUsuario = 'admin' | 'usuario';

/** Cuenta de API para integraciones (`app/api/v1/routes/cuentas_api.py`). */
export interface CuentaApi {
  email: string;
  vigencia_dias: number;
  expira_en: string;
  vigente: boolean;
  creada_por: string | null;
  creada_en: string | null;
  clave_generada_en: string | null;
  ultimo_uso_en: string | null;
}

/** Alta o regeneración: la única vez que se ve la contraseña. */
export interface CuentaApiConClave {
  cuenta: CuentaApi;
  password: string;
}

/** `GET /usuarios` (`app/api/v1/routes/usuarios.py::UsuarioAcceso`). */
export interface UsuarioAcceso {
  email: string;
  rol: RolUsuario;
  /** Administrador de `GOOGLE_ALLOWED_EMAILS`: no se cambia desde el panel. */
  fijo: boolean;
  agregado_por: string | null;
  agregado_en: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  /**
   * El perfil viene en el cuerpo y no dentro del JWT, así que el panel puede
   * pintar el correo y el avatar sin decodificar el token a mano.
   */
  usuario: UsuarioResponse;
}

export interface EmpresaCreate {
  ruc: string;
  /** Nombre visible en el selector de empresas. Opcional: el documento de
   * empresa no guarda razón social, y sin él la lista son solo RUC. */
  nombre?: string;
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
  nombre?: string;
  usuario?: string;
  password?: string;
  sunat_client_id?: string;
  sunat_client_secret?: string;
}

/** `app/schemas/empresa.py::RegistroEmpresa`: quién la dio de alta y cómo. */
export interface RegistroEmpresa {
  modalidad: ModalidadCarga;
  /** Correo de la persona que la registró. */
  por: string;
  fecha: string | null;
  carga_id: string | null;
}

export interface EmpresaResponse {
  id: string;
  ruc: string;
  nombre: string | null;
  usuario: string;
  fecha_creacion: string | null;
  /** Del CIIU guardado al completar el alta o, en las antiguas, del token de SUNAT. */
  rubro: string | null;
  ciiu?: string | null;
  registro?: RegistroEmpresa | null;
  /** A quién se envían los resultados de esta empresa. */
  correos_notificacion?: string[];
  /** Actividades de la ficha RUC; contexto del clasificador contable. */
  actividades_economicas?: ActividadEconomica[];
  /** CIIU que manda al clasificar, elegido en Ajustes. `null` = el principal de SUNAT. */
  ciiu_principal_clasificacion?: string | null;
  /** Última ficha RUC consultada en SUNAT (`POST /empresas/{ruc}/ficha-ruc`). */
  ficha_ruc?: FichaRuc | null;
}

/** `app/schemas/empresa.py::ActividadEconomica`. */
export interface ActividadEconomica {
  /** `PRINCIPAL` o `SECUNDARIA`. */
  tipo: string | null;
  ciiu: string;
  descripcion: string | null;
  /** `sunat` (ficha RUC) o `manual` (agregada en Ajustes). */
  origen?: 'sunat' | 'manual' | null;
}

/** Una clase del catálogo CIIU Rev. 4 (`GET /ciiu`). */
export interface ClaseCiiu {
  ciiu: string;
  descripcion: string;
}

/** `app/api/v1/routes/clasificaciones_frecuentes.py::ClasificacionFrecuente`. */
export interface ClasificacionFrecuente {
  id: string;
  libro: string;
  glosa: string;
  cuenta_base: CuentaClasificada | null;
  cuenta_total: CuentaClasificada | null;
  clasificacion: string;
  subtipo: string;
  confianza: number;
  /** Solo las confiables se reutilizan sin consultar a la IA. */
  confiable: boolean;
  /** `ia` o `usuario` (corregida o confirmada desde el panel). */
  origen: 'ia' | 'usuario';
  usos: number;
  actualizado_en: string | null;
}

/** Ficha de la Consulta RUC de SUNAT (`app/services/sunat/ficha_ruc.py::FichaRuc`). */
export interface FichaRuc {
  ruc: string;
  razon_social: string;
  tipo_contribuyente: string;
  nombre_comercial: string;
  estado: string;
  condicion: string;
  actividades_economicas: { tipo: string; orden: number; ciiu: string; descripcion: string }[];
  comprobantes_autorizados: string[];
  sistema_emision_electronica: string[];
  emisor_electronico_desde: string;
  comprobantes_electronicos: string[];
  consultado_en: string | null;
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

export interface PdfSunat {
  ruta: string;
  bytes: number;
  descargado_en: string | null;
}

/** `GET …/comprobantes/cobertura-sunat` (`app/schemas/comprobante.py::CoberturaSunat`). */
export interface CoberturaSunat {
  total: number;
  con_detalle: number;
  con_pdf: number;
  estado_glosa: Record<EstadoGlosa, number>;
}

export interface ComprobanteResponse {
  glosa?: string;
  observacion?: string;
  /**
   * Con glosa / sin glosa / en evaluación / pendiente, según el tipo de
   * comprobante y si el portal ya se consultó (`app/services/glosa.py`).
   */
  estado_glosa: EstadoGlosa | (string & {});
  /** Recuadro «LEYENDA» del portal; es la glosa cuando los ítems no describen nada. */
  leyenda_sunat: string[];
  detracciones?: {
    tipo: 'pago' | 'npd';
    numero?: string;
    cabecera?: Record<string, unknown>;
    datos: Record<string, unknown>;
  }[];
  detracciones_consultado_en?: string | null;
  /** Marca indDetraccion="D" en la propuesta SUNAT. */
  detraccion: boolean;
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
  /** Campo heredado; el backend devuelve siempre null. */
  analisis: null;
  detalle_sunat: unknown[];
  /**
   * Respaldo descargado del portal SOL. `null` mientras no se haya corrido la
   * descarga de PDFs; `ruta` es relativa a `SUNAT_DATA_DIR` en el servidor.
   */
  pdf_sunat: PdfSunat | null;
  /** Referencia al comprobante que modifica una nota de crédito o débito. Sólo en ventas. */
  documentos_modificados: Record<string, unknown>[];
  /** Vouchers de Apaclla Bot (Yape, Plin…) que pagan este comprobante. */
  pagos?: PagoVoucher[];
  /** `null` mientras el clasificador contable no lo haya procesado. */
  clasificacion_contable?: ClasificacionContable | null;
}

export interface CuentaClasificada {
  codigo: string;
  descripcion: string | null;
}

/** `app/schemas/comprobante.py::ClasificacionContable`. */
export interface ClasificacionContable {
  cuenta_base: CuentaClasificada | null;
  cuenta_total: CuentaClasificada | null;
  clasificacion: string;
  subtipo: string;
  condicion_igv: string;
  centro_costos: string | null;
  /** 0–1. */
  confianza: number;
  confianza_rag: number;
  /** Con `true` la cuenta base no pasa al Excel de Contasis. */
  requiere_revision: boolean;
  razon: string;
  modelo: string;
  clasificado_en: string | null;
  /** `ia` o `memoria` (reutilizada de una clasificación frecuente). */
  origen?: 'ia' | 'memoria';
  memoria_id?: string | null;
  /** Partes del motivo (`razon` es su texto completo, el que va al Excel y al PDF). */
  jerarquia_base?: CuentaClasificada[];
  jerarquia_total?: CuentaClasificada[];
  /** El porqué que dio la IA, sin el rastro técnico del RAG. */
  motivo_ia?: string;
  /** Cómo se reutilizó, si vino de una clasificación frecuente. */
  reutilizado?: string | null;
}

/** `resultado` del job `clasificacion_cuentas`. */
export interface ResultadoClasificacion {
  clasificados: number;
  /** Clasificados con una clasificación frecuente, sin consultar a la IA. */
  reutilizados: number;
  /** Comprobantes en revisión (de cualquier periodo) que recibieron la cuenta al acertar la IA con su glosa. */
  propagados: number;
  requieren_revision: number;
  sin_descripcion: number;
  /** Pendientes del libro que no se clasificaron por no estar «Con glosa». */
  sin_glosa_omitidos: number;
  errores: number;
  contrapartes_con_ciiu: number;
  pendientes_restantes: number;
}

/** `GET /clasificador/estado`. */
export interface EstadoClasificador {
  habilitado: boolean;
  estado: 'deshabilitado' | 'sin_iniciar' | 'cargando' | 'listo' | 'error';
  error: string | null;
  modelo_llm: string | null;
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

export interface ErrorIntento {
  intento: number | null;
  en: string | null;
  error: string;
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
  /** Lo ejecuta la cola durable: sobrevive a reinicios y se reintenta solo. */
  gestionado?: boolean;
  solicitud_id?: string | null;
  intentos?: number;
  max_intentos?: number;
  ultimo_intento_en?: string | null;
  /** Solo en un `pendiente` que ya falló alguna vez: cuándo toca el reintento. */
  siguiente_intento_en?: string | null;
  historial_errores?: ErrorIntento[];
}

export interface JobAceptado {
  job_id: string;
  estado: EstadoJob;
  mensaje: string;
}

/* — payloads de `StatusResponse.datos` — */

/** `POST …/propuesta`. `descartados` = filas que SUNAT trajo y el filtro rechazó. */
export interface ResultadoPropuesta {
  detracciones_job_id?: string;
  nuevos: number;
  actualizados: number;
  descartados: number;
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

/* — extracción (app/services/detalle_service.py) — */

/**
 * `resultado` del job `extraccion_detalles` cuando termina. La misma pasada
 * por el portal SOL extrae el detalle de ítems, descarga el PDF y conserva la glosa.
 */
export interface ResultadoExtraccion {
  procesados: number;
  con_detalle: number;
  sin_detalle: number;
  descargados_pdf: number;
  sin_pdf: number;
  /** Los que el tope de `SUNAT_MAX_COMPROBANTES` dejó para otra vuelta. */
  pendientes: number;
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

export interface ComprobantesPorDia {
  name: string;
  qty: number;
}

export interface DashboardData {
  summary: AnalyticsSummary;
  top_contrapartes: ContraparteTop[];
  comprobantes_por_dia: ComprobantesPorDia[];
  comprobantes: ComprobanteResponse[];
}

/** `app/schemas/comprobante_externo.py`. Los montos llegan como texto ("1234.50"). */
/**
 * `recibido`: espera a que exista su periodo. `integrado`: se copió al periodo.
 * `ya_existia`: el periodo ya lo tenía (o la propuesta SUNAT lo trajo después).
 */
export type EstadoExterno = 'recibido' | 'integrado' | 'ya_existia';

/** Espejo de `app/schemas/voucher.py::PagoVoucher`. */
export interface PagoVoucher {
  id: string;
  /** El del voucher, por su fecha. */
  periodo: string;
  libro: string;
  fuente: string;
  /** Nombre para mostrar: Yape, Plin, Mercado Pago, Niubiz. */
  medio_pago: string;
  /** Código de la Tabla 1 de SUNAT (003, 999…). */
  codigo_medio_pago: string;
  nro_operacion: string;
  fecha: string | null;
  total: string | null;
  moneda: string;
  contraparte: string;
  documento_contraparte: string;
  asociacion: 'auto' | 'manual' | null;
  /** El comprobante que paga, de este periodo o del anterior; `null` si está sin comprobante. */
  serie_numero: string | null;
  periodo_comprobante: string | null;
}

export interface CandidataVoucher {
  periodo: string;
  serie_numero: string;
  razon_social: string;
  fecha_emision: string | null;
  total: string | null;
  moneda: string;
}

/** `GET …/periodos/{periodo}/vouchers`. */
export interface VoucherPeriodo extends PagoVoucher {
  /** Comprobantes del mismo libro, moneda y monto que podría pagar, en su periodo o en el anterior. */
  candidatas: CandidataVoucher[];
}

export interface ComprobanteExternoResponse {
  id: string;
  ruc: string;
  periodo: string;
  estado: EstadoExterno | (string & {});
  creado_en: string;
  id_externo: string;
  libro: Libro;
  fuente: FuenteExterna;
  tipo_evidencia: 'voucher' | 'comprobante' | (string & {});
  tipo_cp: string;
  tipo_cp_descripcion: string;
  serie: string;
  numero: string;
  nro_operacion: string | null;
  fecha_operacion: string | null;
  hora_operacion: string | null;
  moneda: string;
  total: string;
  base_imponible: string | null;
  igv: string | null;
  contraparte: { tipo_doc_identidad?: string; documento?: string; nombre?: string };
  descripcion: string;
  confianza: number | null;
  campos_dudosos: string[];
  dispositivo_id: string;
  enviado_en: string | null;
  tiene_imagen: boolean;
  /** Fila del periodo a la que pasó o que ya lo tenía; `null` mientras espera. */
  comprobante_id?: string | null;
  integrado_en?: string | null;
  /** Su serie-número en el listado del periodo (`?comprobante=`). */
  serie_numero_periodo?: string | null;
  /** Periodo de esa fila; en un voucher puede ser el anterior al suyo. */
  periodo_comprobante?: string | null;
}

export interface ListaComprobantesExternos {
  items: ComprobanteExternoResponse[];
  total: number;
  /** Periodos que tienen externos, para el selector. */
  periodos: string[];
}

export interface CodigoVinculacion {
  codigo: string;
  expira_en: string;
}

/* — alta de empresas (app/schemas/carga_empresas.py) — */

/** Respuesta de `POST /empresas`: la empresa y la carga que completa sus datos. */
export interface EmpresaCreada extends EmpresaResponse {
  carga_id: string;
}

export interface FilaCarga {
  fila: number;
  ruc: string;
  razon_social: string;
  usuario: string;
  estado: EstadoFilaCarga;
  motivos: string[];
  empresa_id: string | null;
  fecha_registro: string | null;
}

export interface ProgresoCarga {
  actual: number;
  total: number;
  mensaje: string;
}

export interface CargaResumen {
  id: string;
  modalidad: ModalidadCarga;
  archivo: string | null;
  registrado_por: string;
  estado: EstadoCarga;
  progreso: ProgresoCarga;
  creado_en: string;
  terminado_en: string | null;
}

export interface CargaEmpresas extends CargaResumen {
  filas: FilaCarga[];
}

export interface CargaAceptada {
  carga_id: string;
}

/* — panel general (app/schemas/resumen_empresas.py) — */

export interface ProcesosPorEstado {
  pendiente: number;
  en_progreso: number;
  completado: number;
  fallido: number;
}

export interface PeriodoResumen {
  periodo: string;
  estado: EstadoPeriodo | null;
}

export interface ResumenEmpresa {
  ruc: string;
  nombre: string | null;
  correos_notificacion: string[];
  total_periodos: number;
  /** Del más reciente al más antiguo. */
  periodos: PeriodoResumen[];
  /** Última descarga SIRE completada; `null` si nunca se hizo. */
  ultima_actualizacion_sire: string | null;
  ultimo_proceso: JobResponse | null;
  procesos_por_estado: ProcesosPorEstado;
}

export interface ResumenEmpresas {
  total_empresas: number;
  /** Ventana, en días, de los procesos terminados que se cuentan. */
  dias: number;
  procesos_por_estado: ProcesosPorEstado;
  empresas: ResumenEmpresa[];
}

/* — solicitudes de procesamiento masivo (app/schemas/solicitudes.py) — */

export interface SolicitudCreate {
  /** RUC de las empresas, o `'todas'`. */
  empresas: string[] | 'todas';
  /** Periodos `YYYYMM`, o `'todos'` (los registrados de cada empresa). */
  periodos: string[] | 'todos';
  clasificar: boolean;
}

export interface PasoSolicitudResponse {
  paso: PasoSolicitud;
  estado: EstadoPasoSolicitud;
  job_id: string | null;
  nota: string | null;
  /** Estado vivo del trabajo que ejecuta el paso. */
  job_estado?: EstadoJob | null;
  intentos?: number | null;
  max_intentos?: number | null;
  siguiente_intento_en?: string | null;
  mensaje?: string | null;
  error?: string | null;
}

export interface ItemSolicitud {
  ruc: string;
  nombre: string | null;
  periodo: string;
  estado: EstadoItemSolicitud;
  observaciones: string[];
  pasos: PasoSolicitudResponse[];
}

export interface EmpresaEnvio {
  ruc: string;
  nombre: string | null;
}

export interface EnvioCorreo {
  correo: string;
  empresas: EmpresaEnvio[];
  periodos: string[];
  estado: EstadoEnvio;
  modo: 'adjunto' | 'enlace' | null;
  intentos: number | null;
  error: string | null;
  creado_en: string | null;
  enviado_en: string | null;
}

export interface EnvioListado extends EnvioCorreo {
  solicitud_id: string;
  solicitud_creada_en: string | null;
}

export interface SolicitudResponse {
  id: string;
  creado_por: string;
  creado_en: string;
  terminado_en: string | null;
  estado: EstadoSolicitud;
  clasificar: boolean;
  error: string | null;
  /** Items (empresa × periodo) terminados de los totales. */
  progreso: { actual: number; total: number };
  items: ItemSolicitud[];
  zip: { archivo: string; bytes: number; generado_en: string | null } | null;
  envios: EnvioCorreo[];
}

/* — configuración del correo (app/schemas/configuracion_correo.py) — */

export type SeguridadSmtp = 'starttls' | 'ssl' | 'ninguna';

export interface VariablePlantilla {
  nombre: string;
  descripcion: string;
}

export interface ConfiguracionCorreo {
  host: string;
  puerto: number;
  seguridad: SeguridadSmtp;
  usuario: string;
  /** La contraseña nunca viaja al navegador; solo si hay una guardada. */
  password_configurada: boolean;
  remitente_nombre: string;
  remitente_correo: string;
  /** Vacía = se puede escribir a cualquiera. */
  destinatarios_permitidos: string[];
  max_adjunto_mb: number;
  dias_enlace: number;
  url_publica: string;
  plantilla_asunto: string;
  plantilla_cuerpo: string;
  configurado: boolean;
  variables: VariablePlantilla[];
  plantilla_por_defecto: { asunto: string; cuerpo: string };
}

/** Cambios parciales. `password` vacío conserva la guardada. */
export type ConfiguracionCorreoUpdate = Partial<
  Omit<
    ConfiguracionCorreo,
    'password_configurada' | 'configurado' | 'variables' | 'plantilla_por_defecto'
  >
> & { password?: string };

export interface VistaPreviaCorreo {
  asunto: string;
  texto: string;
  html: string;
}
