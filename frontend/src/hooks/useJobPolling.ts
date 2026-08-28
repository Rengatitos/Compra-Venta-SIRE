import { useQuery } from '@tanstack/react-query';

import { obtenerJob } from '@/api/jobs';
import type { JobResponse } from '@/types/api';
import { ESTADOS_JOB_TERMINALES } from '@/types/domain';

const INTERVALO_MS = 3000;

/**
 * Sigue un job asíncrono del backend. El sondeo se detiene solo en cuanto el job
 * llega a un estado terminal (`completado` o `fallido`), así que no queda una
 * petición cada 3 s viva indefinidamente.
 */
export function useJobPolling(jobId: string | null) {
  return useQuery<JobResponse>({
    queryKey: ['job', jobId],
    queryFn: () => obtenerJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (consulta) => {
      const estado = consulta.state.data?.estado;
      if (!estado) return INTERVALO_MS;
      return ESTADOS_JOB_TERMINALES.includes(estado) ? false : INTERVALO_MS;
    },
    staleTime: 0,
  });
}
