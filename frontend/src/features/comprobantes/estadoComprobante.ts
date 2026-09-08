import type { TonoInsignia } from '@/components/ui/Badge';
import type { AnalisisIA } from '@/types/api';

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

export interface CuentaPresentada {
  /** Cuenta base del plan Contasis, o `null` si el RAG no encontró ninguna. */
  cuenta: string | null;
  /** Contrapartida (4212, 1212…), si la hay. */
  contrapartida: string | null;
  /** Por qué falta la cuenta, cuando el RAG lo dice. */
  motivo: string | null;
}

/**
 * La cuenta que se muestra es `rag.cuenta_base`; `cuenta_contable` es el
 * mismo dato copiado en el formato antiguo. Cuando falta, el motivo viene
 * dentro de `respuesta_cuentas`, que es el JSON crudo de la clasificación.
 */
export function presentarCuenta(analisis: AnalisisIA | null): CuentaPresentada | null {
  if (!analisis) return null;
  const cuenta = analisis.rag?.cuenta_base || analisis.cuenta_contable || null;
  const contrapartida = analisis.rag?.cuenta_total || null;
  let motivo: string | null = null;
  if (!cuenta && analisis.rag?.respuesta_cuentas) {
    try {
      const crudo: unknown = JSON.parse(analisis.rag.respuesta_cuentas);
      if (crudo && typeof crudo === 'object' && 'datos_faltantes' in crudo) {
        const faltantes: unknown = crudo.datos_faltantes;
        if (Array.isArray(faltantes) && faltantes.length > 0) {
          motivo = faltantes.filter((item) => typeof item === 'string').join(', ');
        }
      }
    } catch {
      // No es JSON: se muestra la cuenta vacía sin motivo.
    }
  }
  return { cuenta, contrapartida, motivo };
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
