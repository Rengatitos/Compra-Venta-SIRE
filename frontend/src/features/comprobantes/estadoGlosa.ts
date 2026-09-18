import type { TonoInsignia } from '@/components/ui/Badge';
import type { EstadoGlosa } from '@/types/domain';

interface Presentacion {
  tono: TonoInsignia;
  texto: string;
}

/** Espejo de `app/services/glosa.py::ETIQUETA_ESTADO_GLOSA`. */
const ESTADOS: Record<EstadoGlosa, Presentacion> = {
  con_glosa: { tono: 'exito', texto: 'Con glosa' },
  sin_glosa: { tono: 'aviso', texto: 'Sin glosa' },
  en_evaluacion: { tono: 'info', texto: 'En evaluación' },
  pendiente: { tono: 'neutro', texto: 'Pendiente' },
};

export function presentarEstadoGlosa(estado: string): Presentacion {
  return (ESTADOS as Record<string, Presentacion>)[estado] ?? { tono: 'neutro', texto: estado };
}
