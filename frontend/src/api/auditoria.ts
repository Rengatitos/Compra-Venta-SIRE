import { pedir, segmento } from '@/lib/http';
import type { ReporteResponse } from '@/types/api';
import type { Libro } from '@/types/domain';

/**
 * `GET …/libros/{libro}/auditoria/reporte`. La tabla comparativa que pidió el
 * auditor: por cada comprobante, lo que declara el registro frente a lo que se
 * leyó del portal, la glosa del RAG, y el bloque `fuentes` que dice de dónde
 * salió cada dato. `404` si el periodo no existe para la empresa.
 */
export function obtenerReporte(
  ruc: string,
  periodo: string,
  libro: Libro,
): Promise<ReporteResponse> {
  return pedir<ReporteResponse>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/libros/${segmento(libro)}` +
      '/auditoria/reporte',
  );
}
