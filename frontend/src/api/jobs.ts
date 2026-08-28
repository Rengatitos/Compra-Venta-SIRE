import { pedir, segmento } from '@/lib/http';
import type { JobResponse } from '@/types/api';

/** `GET /api/v1/jobs/{job_id}`. `403` si el job es de otra empresa. */
export function obtenerJob(jobId: string): Promise<JobResponse> {
  return pedir<JobResponse>(`/jobs/${segmento(jobId)}`);
}
