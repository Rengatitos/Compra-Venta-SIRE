import { pedir, segmento } from '@/lib/http';
import type { JobResponse } from '@/types/api';
import type { EstadoJob, TipoJob } from '@/types/domain';

/** `GET /api/v1/jobs/{job_id}`. `403` si el job es de otra empresa. */
export function obtenerJob(jobId: string): Promise<JobResponse> {
  return pedir<JobResponse>(`/jobs/${segmento(jobId)}`);
}

export interface FiltroJobs {
  periodo?: string;
  tipo?: TipoJob;
  estado?: EstadoJob;
  limit?: number;
  skip?: number;
}

/**
 * `GET /api/v1/jobs`. El RUC no es un parámetro: el backend lo saca del token,
 * así que la lista siempre es la de la empresa autenticada. Viene ordenada del
 * job más reciente al más antiguo.
 */
export function listarJobs(filtro: FiltroJobs = {}): Promise<JobResponse[]> {
  return pedir<JobResponse[]>('/jobs', { consulta: { ...filtro } });
}
