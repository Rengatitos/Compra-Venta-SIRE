import { pedir, segmento } from '@/lib/http';
import type { ClasificacionContable, EstadoClasificador, JobAceptado } from '@/types/api';
import type { Libro } from '@/types/domain';

/**
 * `POST …/libros/{libro}/clasificacion`. Job que asigna la cuenta contable
 * (RAG + Gemini) a los comprobantes del libro que aún no la tienen; con
 * `reclasificar`, a todos. `503` si el clasificador está deshabilitado.
 */
export function iniciarClasificacion(
  ruc: string,
  periodo: string,
  libro: Libro,
  reclasificar = false,
): Promise<JobAceptado> {
  return pedir<JobAceptado>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/libros/${segmento(libro)}/clasificacion`,
    { metodo: 'POST', consulta: { reclasificar } },
  );
}

/** Clasifica un comprobante en el acto (unos segundos) y guarda el resultado. */
export function clasificarComprobante(
  ruc: string,
  periodo: string,
  serieNumero: string,
  libro: Libro,
): Promise<ClasificacionContable> {
  return pedir<ClasificacionContable>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/comprobantes/${segmento(serieNumero)}/clasificacion`,
    { metodo: 'POST', consulta: { libro } },
  );
}

export function obtenerEstadoClasificador(): Promise<EstadoClasificador> {
  return pedir<EstadoClasificador>('/clasificador/estado');
}
