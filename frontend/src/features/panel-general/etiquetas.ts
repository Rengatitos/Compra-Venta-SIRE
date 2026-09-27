import type { Libro } from '@/types/domain';

export const ETIQUETA_LIBRO: Record<Libro, string> = {
  compras: 'Compras',
  ventas: 'Ventas',
};

/** Periodos que se ven por empresa en la tabla; el resto se resume en «+N más». */
export const PERIODOS_VISIBLES = 6;
