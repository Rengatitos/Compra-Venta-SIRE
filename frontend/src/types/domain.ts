/**
 * Uniones literales que reflejan los enums de `app/domain/`. Se mantienen como
 * uniones (no enums de TS) para que el JSON del backend encaje sin conversión.
 */

/** `app/domain/comprobante.py::Libro`. */
export const LIBROS = ['compras', 'ventas'] as const;
export type Libro = (typeof LIBROS)[number];

/** `app/domain/comprobante.py::EstadoProcesamiento`. */
export type EstadoProcesamiento =
  'sire_recibido' | 'analizado' | 'error_analisis' | 'sin_datos';

/**
 * `app/services/glosa.py::estado_glosa`. Depende del tipo de comprobante (qué
 * publica SUNAT) y de si el portal ya se consultó: «pendiente» es un tipo
 * consultable que todavía no pasó por SOL.
 */
export const ESTADOS_GLOSA = ['con_glosa', 'sin_glosa', 'en_evaluacion', 'pendiente'] as const;
export type EstadoGlosa = (typeof ESTADOS_GLOSA)[number];

/** `app/domain/jobs.py::EstadoJob`. */
export type EstadoJob = 'pendiente' | 'en_progreso' | 'completado' | 'fallido';

export const ESTADOS_JOB_TERMINALES: readonly EstadoJob[] = ['completado', 'fallido'];

/** `app/domain/jobs.py::TipoJob`. */
export type TipoJob =
  | 'extraccion_detalles'
  | 'descarga_pdfs'
  | 'detracciones'
  | 'clasificacion_cuentas'
  | 'sincronizacion_sire'
  | 'alta_empresa'
  | 'credenciales_sunat'
  | 'empaquetado'
  | 'envio_correo';

/** `app/domain/carga_empresas.py::EstadoFila`. */
export type EstadoFilaCarga =
  'pendiente' | 'agregada' | 'agregada_con_observaciones' | 'no_agregada';

/** `app/domain/carga_empresas.py::EstadoCarga`. */
export type EstadoCarga = 'en_progreso' | 'completada';

/** `app/domain/carga_empresas.py::Modalidad`. */
export type ModalidadCarga = 'individual' | 'masiva';

/**
 * Fuentes que respaldan un dato del reporte, de menos a más cerca del
 * documento original (`app/api/v1/routes/auditoria.py`). Es lo que el auditor
 * usa para rastrear de dónde salió cada importe.
 */
export type FuenteDato = 'propuesta_sire' | 'detalle_portal_sol' | 'pdf_descargado';

/**
 * Estados de periodo. `sincronizado` y `sin_propuesta` los escribe el propio
 * backend (`propuesta_service.py`); el resto son valores libres editables por
 * `PUT /periodos/{periodo}`.
 */
export type EstadoPeriodo = 'pendiente' | 'sincronizado' | 'sin_propuesta' | (string & {});

export const FORMATOS_EXPORT = ['excel', 'pdf'] as const;
export type FormatoExport = (typeof FORMATOS_EXPORT)[number];

/** Formato `YYYYMM` validado por `app/domain/periodo.py::PERIODO_RE`. */
const PERIODO_RE = /^20\d{2}(0[1-9]|1[0-2])$/;

export function esPeriodoValido(periodo: string): boolean {
  return PERIODO_RE.test(periodo);
}

const PESOS_RUC = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
const PREFIJOS_RUC = new Set(['10', '15', '17', '20']);

/**
 * Espejo de `app/domain/carga_empresas.py::es_ruc_valido`: 11 dígitos, prefijo
 * de contribuyente y dígito verificador módulo 11. Así un RUC mal tecleado se
 * rechaza en el navegador y no tras un viaje al servidor.
 */
export function esRucValido(ruc: string): boolean {
  const valor = ruc.trim();
  if (!/^\d{11}$/.test(valor) || !PREFIJOS_RUC.has(valor.slice(0, 2))) return false;
  const suma = PESOS_RUC.reduce((total, peso, i) => total + Number(valor[i]) * peso, 0);
  const resto = 11 - (suma % 11);
  const verificador = resto === 10 ? 0 : resto === 11 ? 1 : resto;
  return verificador === Number(valor[10]);
}

/** `app/domain/comprobante_externo.py::Fuente`: de qué foto salió el comprobante. */
export type FuenteExterna =
  'yape' | 'plin' | 'mercado_pago' | 'niubiz' | 'boleta' | 'factura' | 'otro' | (string & {});

/** `app/domain/solicitudes.py::EstadoSolicitud`. */
export type EstadoSolicitud =
  | 'en_progreso'
  | 'empaquetando'
  | 'enviando'
  | 'completada'
  | 'completada_con_errores'
  | 'fallida';

export const ESTADOS_SOLICITUD_TERMINALES: readonly EstadoSolicitud[] = [
  'completada',
  'completada_con_errores',
  'fallida',
];

/** `app/domain/solicitudes.py::EstadoItem`. */
export type EstadoItemSolicitud =
  'pendiente' | 'en_progreso' | 'completado' | 'con_errores' | 'fallido';

/** `app/domain/solicitudes.py::EstadoPaso`. */
export type EstadoPasoSolicitud =
  'pendiente' | 'encolado' | 'completado' | 'fallido' | 'omitido';

/** `app/domain/solicitudes.py::Paso`, en el orden en que se ejecutan. */
export const PASOS_SOLICITUD = [
  'credenciales',
  'sire_compras',
  'sire_ventas',
  'detalle_compras',
  'detalle_ventas',
  'clasificacion_compras',
  'clasificacion_ventas',
] as const;
export type PasoSolicitud = (typeof PASOS_SOLICITUD)[number];

/** `app/domain/solicitudes.py::EstadoEnvio`. */
export type EstadoEnvio = 'pendiente' | 'enviado' | 'fallido' | 'bloqueado';
