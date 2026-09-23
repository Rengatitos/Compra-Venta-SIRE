import { pedir, segmento } from '@/lib/http';
import type {
  ClasificacionContable,
  ClasificacionFrecuente,
  CuentaClasificada,
  EstadoClasificador,
  JobAceptado,
} from '@/types/api';
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

/**
 * Clasifica un comprobante en el acto y guarda el resultado. Con `usarMemoria`
 * reutiliza una clasificación frecuente con la misma glosa si la hay (al
 * instante); sin ella va siempre a la IA (unos segundos).
 */
export function clasificarComprobante(
  ruc: string,
  periodo: string,
  serieNumero: string,
  libro: Libro,
  usarMemoria = true,
): Promise<ClasificacionContable> {
  return pedir<ClasificacionContable>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/comprobantes/${segmento(serieNumero)}/clasificacion`,
    { metodo: 'POST', consulta: { libro, usar_memoria: usarMemoria } },
  );
}

const frecuentes = (ruc: string) => `/empresas/${segmento(ruc)}/clasificaciones-frecuentes`;

export function listarClasificacionesFrecuentes(
  ruc: string,
  libro?: Libro,
): Promise<ClasificacionFrecuente[]> {
  return pedir<ClasificacionFrecuente[]>(frecuentes(ruc), { consulta: { libro } });
}

/**
 * Corrige (o confirma) una clasificación frecuente: pasa a reutilizarse y se
 * aplica a los comprobantes que ya la usaban.
 */
export function corregirClasificacionFrecuente(
  ruc: string,
  id: string,
  cuentaBase: CuentaClasificada,
  cuentaTotal?: CuentaClasificada | null,
): Promise<ClasificacionFrecuente> {
  return pedir<ClasificacionFrecuente>(`${frecuentes(ruc)}/${segmento(id)}`, {
    metodo: 'PATCH',
    cuerpo: { cuenta_base: cuentaBase, cuenta_total: cuentaTotal ?? null },
  });
}

export function eliminarClasificacionFrecuente(ruc: string, id: string): Promise<void> {
  return pedir<void>(`${frecuentes(ruc)}/${segmento(id)}`, { metodo: 'DELETE' });
}

export function obtenerEstadoClasificador(): Promise<EstadoClasificador> {
  return pedir<EstadoClasificador>('/clasificador/estado');
}
