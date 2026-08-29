import { useContext } from 'react';

import { ContextoJobsReact } from './jobsContext';
import type { ContextoJobs } from './jobsContext';

export function useJobs(): ContextoJobs {
  const contexto = useContext(ContextoJobsReact);
  if (!contexto) {
    throw new Error('useJobs necesita estar dentro de <JobsProvider>.');
  }
  return contexto;
}
