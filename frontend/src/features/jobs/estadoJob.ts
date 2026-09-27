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
  extraccion_detalles: 'Detalle y PDF SUNAT',
  descarga_pdfs: 'Descarga de PDFs',
  detracciones: 'Consulta de detracciones',
  clasificacion_cuentas: 'Clasificación contable',
  sincronizacion_sire: 'Descarga SIRE',
  alta_empresa: 'Alta de empresa',
  credenciales_sunat: 'Credenciales del API SUNAT',
  empaquetado: 'Archivos y ZIP',
  envio_correo: 'Envío de correo',
};

export function presentarTipoJob(tipo: string): string {
  return TIPOS[tipo as TipoJob] ?? tipo;
}

/** Opciones para filtrar por estado, en el orden en que avanza un trabajo. */
export const OPCIONES_ESTADO_JOB: readonly { valor: EstadoJob; texto: string }[] = (
  ['pendiente', 'en_progreso', 'completado', 'fallido'] as const
).map((valor) => ({ valor, texto: ESTADOS[valor].texto }));

export const OPCIONES_TIPO_JOB: readonly { valor: TipoJob; texto: string }[] = (
  Object.entries(TIPOS) as [TipoJob, string][]
).map(([valor, texto]) => ({ valor, texto }));

/**
 * Un trabajo de la cola que falló y espera su reintento sigue `pendiente`; lo
 * que lo distingue de uno que aún no empezó es que ya lleva intentos. Se
 * cuenta en voz alta para que no parezca colgado.
 */
export function describirReintento(job: {
  estado: EstadoJob;
  intentos?: number;
  max_intentos?: number;
}): string | null {
  const intentos = job.intentos ?? 0;
  const maximo = job.max_intentos ?? 1;
  if (job.estado === 'pendiente' && intentos > 0) {
    return `Reintento ${intentos + 1} de ${maximo}`;
  }
  if (job.estado === 'fallido' && maximo > 1) {
    return `Falló tras ${intentos} ${intentos === 1 ? 'intento' : 'intentos'}`;
  }
  return null;
}
