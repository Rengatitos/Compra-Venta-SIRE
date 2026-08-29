import { createContext } from 'react';

import type { JobResponse } from '@/types/api';

export interface ContextoJobs {
  /** Ids que esta pestaña está siguiendo, terminados o no. */
  seguidos: readonly string[];
  /** Último estado conocido de cada id seguido, indexado por `job_id`. */
  porId: Readonly<Record<string, JobResponse>>;
  /** Registra un job recién lanzado para que se siga desde cualquier pantalla. */
  seguir: (jobId: string) => void;
  dejarDeSeguir: (jobId: string) => void;
}

export const ContextoJobsReact = createContext<ContextoJobs | null>(null);
