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

/** Espejo de los estados de `app/domain/comprobante_externo.py`. */
const ESTADOS: Record<string, Presentacion> = {
  recibido: { tono: 'aviso', texto: 'Esperando periodo' },
  integrado: { tono: 'info', texto: 'En el periodo' },
  ya_existia: { tono: 'neutro', texto: 'Ya existía en el periodo' },
};

/**
 * Un voucher no es una fila del periodo sino el pago de un comprobante: en el
 * periodo está asociado a uno o queda «sin comprobante».
 */
export function presentarEstado(fila: {
  estado: string;
  tipo_evidencia: string;
  serie_numero_periodo?: string | null;
}): Presentacion {
  if (fila.tipo_evidencia === 'voucher' && fila.estado === 'integrado') {
    return fila.serie_numero_periodo
      ? { tono: 'info', texto: `Pago de ${fila.serie_numero_periodo}` }
      : { tono: 'aviso', texto: 'Sin comprobante' };
  }
  return ESTADOS[fila.estado] ?? { tono: 'neutro', texto: fila.estado };
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
