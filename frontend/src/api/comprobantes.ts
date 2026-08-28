import { descargar, pedir, segmento } from '@/lib/http';
import type { ComprobanteResponse, MessageResponse } from '@/types/api';
import type { FormatoExport, Libro } from '@/types/domain';

const base = (ruc: string, periodo: string) =>
  `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/comprobantes`;

const EXTENSION: Record<FormatoExport, string> = { excel: 'xlsx', pdf: 'pdf' };

export interface FiltroComprobantes {
  libro?: Libro;
  limit?: number;
  skip?: number;
}

/** `404` si el periodo no existe para la empresa. */
export function listarComprobantes(
  ruc: string,
  periodo: string,
  filtro: FiltroComprobantes = {},
): Promise<ComprobanteResponse[]> {
  return pedir<ComprobanteResponse[]>(base(ruc, periodo), {
    consulta: {
      libro: filtro.libro,
      limit: filtro.limit ?? 100,
      skip: filtro.skip ?? 0,
    },
  });
}

export function obtenerComprobante(
  ruc: string,
  periodo: string,
  serieNumero: string,
): Promise<ComprobanteResponse> {
  return pedir<ComprobanteResponse>(`${base(ruc, periodo)}/${segmento(serieNumero)}`);
}

/** El único campo editable es la descripción del análisis. */
export function actualizarDescripcion(
  ruc: string,
  periodo: string,
  serieNumero: string,
  descripcion: string,
): Promise<MessageResponse> {
  return pedir<MessageResponse>(`${base(ruc, periodo)}/${segmento(serieNumero)}`, {
    metodo: 'PATCH',
    cuerpo: { descripcion },
  });
}

/** Hasta 5000 comprobantes del periodo. `404` si el periodo está vacío. */
export function exportarLote(
  ruc: string,
  periodo: string,
  formato: FormatoExport,
): Promise<void> {
  return descargar(
    `${base(ruc, periodo)}/export`,
    `comprobantes_${periodo}.${EXTENSION[formato]}`,
    { formato },
  );
}

export function exportarComprobante(
  ruc: string,
  periodo: string,
  serieNumero: string,
  formato: FormatoExport,
): Promise<void> {
  return descargar(
    `${base(ruc, periodo)}/${segmento(serieNumero)}/export`,
    `comprobante_${serieNumero}.${EXTENSION[formato]}`,
    { formato },
  );
}
