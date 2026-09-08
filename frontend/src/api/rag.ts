import { pedir } from '@/lib/http';
import type { EstadoRag } from '@/types/api';

/**
 * `GET /rag/estado`. Cuántas filas tiene cada índice del RAG contable.
 *
 * Con `cuentas` en cero el clasificador no puede devolver ninguna cuenta y la
 * columna sale en blanco para todos los comprobantes: la pantalla lo consulta
 * para explicarlo en vez de mostrar un guion sin más.
 */
export function estadoRag(): Promise<EstadoRag> {
  return pedir<EstadoRag>('/rag/estado');
}
