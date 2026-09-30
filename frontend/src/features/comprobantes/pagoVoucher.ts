import type { PagoVoucher } from '@/types/api';

/** `Yape · Op. 12345678`: lo que identifica un voucher en una línea. */
export function presentarPago(pago: PagoVoucher): string {
  return `${pago.medio_pago} · Op. ${pago.nro_operacion}`;
}
