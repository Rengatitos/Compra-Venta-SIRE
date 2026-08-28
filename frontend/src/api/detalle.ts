import { pedir, segmento } from '@/lib/http';
import type { JobAceptado } from '@/types/api';

/**
 * `POST …/detalle`. Responde `202` con un `job_id`: el scraping del portal SOL
 * corre en segundo plano y su avance se consulta en `GET /jobs/{job_id}`.
 * Límite 5/min.
 */
export function iniciarExtraccionDetalle(ruc: string, periodo: string): Promise<JobAceptado> {
  return pedir<JobAceptado>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/detalle`,
    { metodo: 'POST' },
  );
}
