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
 * `app/domain/jobs.py::TipoJob`. Hoy solo existe `extraccion_detalles`, pero el
 * contrato está pensado para crecer, así que el nombre técnico nunca llega
 * crudo a la pantalla.
 */
const TIPOS: Record<TipoJob, string> = {
  extraccion_detalles: 'Extracción de detalle',
};

export function presentarTipoJob(tipo: string): string {
  return TIPOS[tipo as TipoJob] ?? tipo;
}
