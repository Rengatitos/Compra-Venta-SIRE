import type { TonoInsignia } from '@/components/ui/Badge';
import type { FuenteExterna } from '@/types/domain';

interface Presentacion {
  tono: TonoInsignia;
  texto: string;
}

/** Espejo de `app/domain/comprobante_externo.py::Fuente`. */
const FUENTES: Record<string, Presentacion> = {
  yape: { tono: 'info', texto: 'Yape' },
  plin: { tono: 'info', texto: 'Plin' },
  mercado_pago: { tono: 'info', texto: 'Mercado Pago' },
  niubiz: { tono: 'info', texto: 'Niubiz' },
  boleta: { tono: 'neutro', texto: 'Boleta' },
  factura: { tono: 'neutro', texto: 'Factura' },
  otro: { tono: 'neutro', texto: 'Otro' },
};

export function presentarFuente(fuente: FuenteExterna): Presentacion {
  return FUENTES[fuente] ?? { tono: 'neutro', texto: fuente };
}

/** Lo que identifica al comprobante: serie-número o, en un voucher, la operación. */
export function identificador(fila: {
  serie: string;
  numero: string;
  nro_operacion: string | null;
}): string {
  if (fila.serie && fila.numero) return `${fila.serie}-${fila.numero}`;
  if (fila.nro_operacion) return `Op. ${fila.nro_operacion}`;
  return '—';
}

const CAMPOS: Record<string, string> = {
  total: 'total',
  moneda: 'moneda',
  fecha_operacion: 'fecha',
  hora_operacion: 'hora',
  nro_operacion: 'n.º de operación',
  serie: 'serie',
  numero: 'número',
  contraparte: 'contraparte',
  descripcion: 'descripción',
  igv: 'IGV',
  base_imponible: 'base imponible',
};

export function nombreCampo(campo: string): string {
  return CAMPOS[campo] ?? campo.replace(/_/g, ' ');
}
