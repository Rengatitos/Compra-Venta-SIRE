import type { TonoInsignia } from '@/components/ui/Badge';

interface Presentacion {
  tono: TonoInsignia;
  texto: string;
}

/** Espejo de `app/domain/comprobante.py::EstadoProcesamiento`. */
const ESTADOS: Record<string, Presentacion> = {
  sire_recibido: { tono: 'neutro', texto: 'Sincronizado' },
  analizado: { tono: 'exito', texto: 'Analizado' },
  error_analisis: { tono: 'error', texto: 'Error de análisis' },
  sin_datos: { tono: 'aviso', texto: 'Sin datos' },
};

/** Las filas `origen: "externo"` llegaron desde Apaclla Bot, no de la propuesta SUNAT. */
export const ORIGEN_EXTERNO = 'externo';

export function esExterno(fila: { origen: string }): boolean {
  return fila.origen === ORIGEN_EXTERNO;
}

export function presentarEstadoComprobante(estado: string): Presentacion {
  return ESTADOS[estado] ?? { tono: 'neutro', texto: estado };
}
