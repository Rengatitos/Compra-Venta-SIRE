import { pedir, segmento } from '@/lib/http';
import type { JobResponse } from '@/types/api';
import type { EstadoJob, TipoJob } from '@/types/domain';

/**
 * `GET /api/v1/jobs/{job_id}`. Un `job_id` es único, y la sesión da acceso a
 * todas las empresas, así que no lleva RUC: solo puede fallar con `404`.
 */
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
 * `GET /api/v1/jobs`. El RUC va explícito: el token identifica a una persona
 * con acceso a todas las empresas, así que ya no puede deducirse de él. Sin RUC
 * el backend devuelve el historial de todas. Viene ordenada del job más reciente
 * al más antiguo.
 */
export function listarJobs(ruc: string, filtro: FiltroJobs = {}): Promise<JobResponse[]> {
  return pedir<JobResponse[]>('/jobs', { consulta: { ruc, ...filtro } });
}
