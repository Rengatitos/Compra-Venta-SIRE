import type { ComprobanteResponse } from '@/types/api';

import { formatearMoneda } from './format';

/** Los importes SIRE están en PEN; moneda identifica la moneda del comprobante. */
export function formatearImporteComprobante(
  importe: number,
  comprobante: Pick<ComprobanteResponse, 'origen' | 'moneda' | 'tipo_cambio'>,
): string {
  const moneda = comprobante.moneda.trim().toUpperCase();
  if (comprobante.origen === 'sire' && moneda !== 'PEN') {
    const tasa = comprobante.tipo_cambio;
    if (tasa !== null && Number.isFinite(tasa) && tasa > 0) {
      return formatearMoneda(importe / tasa, moneda);
    }
    // Sin tasa no se puede expresar en moneda original: mostrar su moneda real.
    return formatearMoneda(importe, 'PEN');
  }
  return formatearMoneda(importe, moneda);
}
