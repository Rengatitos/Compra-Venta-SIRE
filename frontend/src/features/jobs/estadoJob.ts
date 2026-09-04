import type { TonoInsignia } from '@/components/ui/Badge';
import type { EstadoJob, TipoJob } from '@/types/domain';

interface Presentacion {
  tono: TonoInsignia;
  texto: string;
}

/** `app/domain/jobs.py::EstadoJob`. */
const ESTADOS: Record<EstadoJob, Presentacion> = {
  pendiente: { tono: 'neutro', texto: 'En cola' },
  en_progreso: { tono: 'info', texto: 'En progreso' },
  completado: { tono: 'exito', texto: 'Completado' },
  fallido: { tono: 'error', texto: 'Fallido' },
};

export function presentarEstadoJob(estado: EstadoJob): Presentacion {
  return ESTADOS[estado] ?? { tono: 'neutro', texto: estado };
}

/**
 * `app/domain/jobs.py::TipoJob`. El nombre técnico nunca llega crudo a la
 * pantalla: al ser un `Record` completo, añadir un tipo en el backend rompe
 * el typecheck hasta que alguien le da un rótulo legible.
 */
const TIPOS: Record<TipoJob, string> = {
  extraccion_detalles: 'Detalle SUNAT y códigos RAG',
  descarga_pdfs: 'Descarga de PDFs',
};

export function presentarTipoJob(tipo: string): string {
  return TIPOS[tipo as TipoJob] ?? tipo;
}
