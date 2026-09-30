import { pedir, segmento } from '@/lib/http';
import type { PagoVoucher, VoucherPeriodo } from '@/types/api';
import type { Libro } from '@/types/domain';

const base = (ruc: string, periodo: string) =>
  `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/vouchers`;

/** Los vouchers de Apaclla Bot del periodo, asociados o no, con sus candidatas. */
export function listarVouchers(ruc: string, periodo: string, libro: Libro) {
  return pedir<VoucherPeriodo[]>(base(ruc, periodo), { consulta: { libro } });
}

/**
 * Asocia el voucher al comprobante que paga; `null` lo desasocia. El
 * comprobante puede ser del periodo del voucher o del anterior: sin
 * `periodoComprobante` se busca primero en el del voucher.
 */
export function asociarVoucher(
  ruc: string,
  periodo: string,
  voucherId: string,
  serieNumero: string | null,
  periodoComprobante?: string,
) {
  return pedir<PagoVoucher>(`${base(ruc, periodo)}/${segmento(voucherId)}/asociacion`, {
    metodo: 'PUT',
    cuerpo: { serie_numero: serieNumero, periodo: periodoComprobante },
  });
}
