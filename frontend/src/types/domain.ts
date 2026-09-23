/**
 * Uniones literales que reflejan los enums de `app/domain/`. Se mantienen como
 * uniones (no enums de TS) para que el JSON del backend encaje sin conversión.
 */

/** `app/domain/comprobante.py::Libro`. */
export const LIBROS = ['compras', 'ventas'] as const;
export type Libro = (typeof LIBROS)[number];

/** `app/domain/comprobante.py::EstadoProcesamiento`. */
export type EstadoProcesamiento =
  | 'sire_recibido'
  | 'analizado'
  | 'error_analisis'
  | 'sin_datos';

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
  | 'clasificacion_cuentas';

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

/** Espejo de `app/schemas/empresa.py::EmpresaBase.validar_ruc`. */
export function esRucValido(ruc: string): boolean {
  return /^\d{11}$/.test(ruc.trim());
}

/** `app/domain/comprobante_externo.py::Fuente`: de qué foto salió el comprobante. */
export type FuenteExterna =
  | 'yape'
  | 'plin'
  | 'mercado_pago'
  | 'niubiz'
  | 'boleta'
  | 'factura'
  | 'otro'
  | (string & {});
