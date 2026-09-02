import { pedir, segmento } from '@/lib/http';
import type { JobAceptado } from '@/types/api';
import type { Libro } from '@/types/domain';

/**
 * `POST …/libros/{libro}/detalle`. Responde `202` con un `job_id`: el scraping
 * del portal SOL corre en segundo plano y su avance se consulta en
 * `GET /jobs/{job_id}`. Límite 5/min.
 *
 * El libro decide en qué bandeja del portal busca el scraper —«FE Recibidas»
 * para compras, «FE Emitidas» para ventas—, así que va en la ruta. Sólo cabe
 * una extracción a la vez por empresa (`409`): el navegador y la sesión SOL
 * son únicos.
 */
export function iniciarExtraccionDetalle(
  ruc: string,
  periodo: string,
  libro: Libro,
): Promise<JobAceptado> {
  return pedir<JobAceptado>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/libros/${segmento(libro)}/detalle`,
    { metodo: 'POST' },
  );
}
