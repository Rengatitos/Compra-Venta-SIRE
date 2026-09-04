import type { TonoInsignia } from '@/components/ui/Badge';
import type { ComprobanteResponse, FilaReporte } from '@/types/api';
import type { FuenteDato } from '@/types/domain';

interface Presentacion {
  tono: TonoInsignia;
  texto: string;
}

const SI: Presentacion = { tono: 'exito', texto: 'Sí' };
const NO: Presentacion = { tono: 'neutro', texto: 'No' };

/**
 * Qué respaldo tiene un comprobante para la auditoría. Se presenta como tres
 * respuestas independientes en vez de un estado único porque las tres se
 * consiguen por caminos distintos —la propuesta, el scraping del portal y la
 * clasificación de la IA— y al auditor le importa cuál falta, no un promedio.
 */
export function tieneDetalle(comprobante: ComprobanteResponse): Presentacion {
  return comprobante.detalle_sunat.length > 0 ? SI : NO;
}

export function tienePdf(comprobante: ComprobanteResponse): Presentacion {
  return comprobante.pdf_sunat?.ruta ? SI : NO;
}

export function tieneGlosa(comprobante: ComprobanteResponse): Presentacion {
  const analisis = comprobante.analisis;
  const glosa = analisis?.rag?.glosa || analisis?.descripcion;
  return glosa ? SI : NO;
}

/** Rótulos de las fuentes del reporte, de menos a más cerca del original. */
const FUENTES: Record<FuenteDato, Presentacion> = {
  propuesta_sire: { tono: 'info', texto: 'Propuesta SIRE' },
  detalle_portal_sol: { tono: 'aviso', texto: 'Portal SOL' },
  pdf_descargado: { tono: 'exito', texto: 'PDF' },
};

export function presentarFuente(fuente: FuenteDato): Presentacion {
  return FUENTES[fuente] ?? { tono: 'neutro', texto: fuente };
}

/**
 * Si la fila no cuadra. `diferencia` viene en `null` cuando no hubo con qué
 * comparar, y eso **no** es un cuadre: es un dato que falta. Confundirlos haría
 * que un periodo sin detalle extraído se viera como un periodo conciliado.
 */
export function descuadra(fila: FilaReporte): boolean {
  return fila.diferencia !== null && Math.abs(fila.diferencia) > 0.01;
}

export function comparable(fila: FilaReporte): boolean {
  return fila.diferencia !== null;
}
