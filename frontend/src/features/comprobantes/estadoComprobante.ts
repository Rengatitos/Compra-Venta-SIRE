import type { TonoInsignia } from '@/components/ui/Badge';

interface Presentacion {
  tono: TonoInsignia;
  texto: string;
}

/** Espejo de `app/domain/comprobante.py::EstadoProcesamiento`. */
const ESTADOS: Record<string, Presentacion> = {
  sire_recibido: { tono: 'neutro', texto: 'Pendiente de análisis' },
  analizado: { tono: 'exito', texto: 'Analizado' },
  error_analisis: { tono: 'error', texto: 'Error de análisis' },
  sin_datos: { tono: 'aviso', texto: 'Sin datos' },
};

export function presentarEstadoComprobante(estado: string): Presentacion {
  return ESTADOS[estado] ?? { tono: 'neutro', texto: estado };
}

/** Tono de la clasificación contable que devuelve la IA. */
export function presentarResultadoIA(resultado: string | null): Presentacion | null {
  if (!resultado) return null;
  const normalizado = resultado.toUpperCase();
  if (normalizado.includes('GASTO')) return { tono: 'info', texto: 'Gasto' };
  if (normalizado.includes('COSTO')) return { tono: 'info', texto: 'Costo' };
  if (normalizado.includes('MIXTO')) return { tono: 'aviso', texto: 'Mixto' };
  return { tono: 'neutro', texto: resultado };
}
