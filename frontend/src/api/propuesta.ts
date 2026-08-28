import { pedir, segmento } from '@/lib/http';
import type { ResultadoPropuesta, StatusResponse } from '@/types/api';
import type { Libro } from '@/types/domain';

/**
 * `POST …/libros/{libro}/propuesta`. Límite 10/min.
 *
 * Con `libro=ventas` el backend responde 501 (el RVIE no está implementado), y
 * si SUNAT no tiene propuesta el periodo queda en `sin_propuesta` con
 * `nuevos: 0` — eso no es un error.
 */
export function sincronizarPropuesta(
  ruc: string,
  periodo: string,
  libro: Libro,
): Promise<StatusResponse<ResultadoPropuesta>> {
  return pedir<StatusResponse<ResultadoPropuesta>>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/libros/${segmento(libro)}/propuesta`,
    { metodo: 'POST' },
  );
}
