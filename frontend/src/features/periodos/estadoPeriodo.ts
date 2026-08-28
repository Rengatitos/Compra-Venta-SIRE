import type { TonoInsignia } from '@/components/ui/Badge';
import type { EstadoPeriodo } from '@/types/domain';

interface Presentacion {
  tono: TonoInsignia;
  texto: string;
  /** Explicación para el usuario; los estados de SUNAT no son obvios. */
  detalle: string;
}

/**
 * `sincronizado` y `sin_propuesta` los escribe el backend
 * (`propuesta_service.py`). `sin_propuesta` NO es un error: significa que SUNAT
 * no tiene propuesta para ese periodo.
 */
const CONOCIDOS: Record<string, Presentacion> = {
  sincronizado: {
    tono: 'exito',
    texto: 'Sincronizado',
    detalle: 'La propuesta del SIRE ya se descargó para este periodo.',
  },
  sin_propuesta: {
    tono: 'aviso',
    texto: 'Sin propuesta',
    detalle: 'SUNAT no tiene propuesta para este periodo. No es un error.',
  },
  pendiente: {
    tono: 'neutro',
    texto: 'Pendiente',
    detalle: 'Todavía no se ha sincronizado la propuesta del SIRE.',
  },
};

export function presentarEstadoPeriodo(estado: EstadoPeriodo): Presentacion {
  return (
    CONOCIDOS[estado] ?? {
      tono: 'neutro',
      texto: estado,
      detalle: 'Estado personalizado del periodo.',
    }
  );
}
