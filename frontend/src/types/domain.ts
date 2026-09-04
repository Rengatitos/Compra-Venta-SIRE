/**
 * Uniones literales que reflejan los enums de `app/domain/`. Se mantienen como
 * uniones (no enums de TS) para que el JSON del backend encaje sin conversión.
 */

/** `app/domain/comprobante.py::Libro`. */
export const LIBROS = ['compras', 'ventas'] as const;
export type Libro = (typeof LIBROS)[number];

/**
 * `libro=ventas` responde 501: el RVIE no tiene cliente HTTP todavía
 * (ver `app/services/sunat/propuesta.py`). La UI ofrece solo lo implementado.
 */
export const LIBROS_IMPLEMENTADOS: readonly Libro[] = ['compras'];

/** `app/domain/comprobante.py::EstadoProcesamiento`. */
export type EstadoProcesamiento =
  | 'sire_recibido'
  | 'analizado'
  | 'error_analisis'
  | 'sin_datos';

/** `app/domain/jobs.py::EstadoJob`. */
export type EstadoJob = 'pendiente' | 'en_progreso' | 'completado' | 'fallido';

export const ESTADOS_JOB_TERMINALES: readonly EstadoJob[] = ['completado', 'fallido'];

/** `app/domain/jobs.py::TipoJob`. */
export type TipoJob = 'extraccion_detalles' | 'descarga_pdfs';

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

/** Resultado de la clasificación de la IA, tal como lo agrupa analytics_service. */
export type ResultadoIA = 'GASTO' | 'COSTO' | 'MIXTO' | 'OTROS';

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
