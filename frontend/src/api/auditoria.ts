import { descargar, pedir, segmento } from '@/lib/http';
import type { ReporteResponse } from '@/types/api';
import type { Libro } from '@/types/domain';

export interface EstadoReporteAsociado {
  habilitado: boolean;
  pendientes: number;
}

/**
 * `GET …/libros/{libro}/auditoria/reporte`. La tabla comparativa que pidió el
 * auditor: por cada comprobante, lo que declara el registro frente a lo que se
 * leyó del portal, la glosa de SUNAT, y el bloque `fuentes` que dice de dónde
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

export function obtenerEstadoReporteAsociado(
  ruc: string,
  periodo: string,
): Promise<EstadoReporteAsociado> {
  return pedir<EstadoReporteAsociado>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/reporte-asociado/estado`,
  );
}

export function descargarReporteAsociado(ruc: string, periodo: string): Promise<void> {
  return descargar(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/reporte-asociado`,
    `reporte_asociado_${periodo}.zip`,
  );
}
