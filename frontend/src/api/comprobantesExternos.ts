import { pedir, pedirBlob, segmento } from '@/lib/http';
import type { ComprobanteExternoResponse, ListaComprobantesExternos } from '@/types/api';
import type { Libro } from '@/types/domain';

const base = (ruc: string) => `/empresas/${segmento(ruc)}/comprobantes-externos`;

export const POR_PAGINA_EXTERNOS = 100;

export interface FiltrosExternos {
  libro: Libro;
  periodo?: string | null;
  pagina?: number;
}

/** `GET …/comprobantes-externos`. Lo que registró Apaclla Bot para la empresa. */
export function listarComprobantesExternos(
  ruc: string,
  { libro, periodo, pagina = 1 }: FiltrosExternos,
): Promise<ListaComprobantesExternos> {
  return pedir<ListaComprobantesExternos>(base(ruc), {
    consulta: {
      libro,
      periodo: periodo || undefined,
      limit: POR_PAGINA_EXTERNOS,
      skip: (pagina - 1) * POR_PAGINA_EXTERNOS,
    },
  });
}

export function obtenerComprobanteExterno(
  ruc: string,
  id: string,
): Promise<ComprobanteExternoResponse> {
  return pedir<ComprobanteExternoResponse>(`${base(ruc)}/${segmento(id)}`);
}

/** La foto que mandó el bot. Va con el Bearer, por eso no es un `<img src>` directo. */
export function descargarImagenExterna(ruc: string, id: string, signal?: AbortSignal) {
  return pedirBlob(`${base(ruc)}/${segmento(id)}/imagen`, signal);
}
