import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './http';

/**
 * Reintentar un 4xx no arregla nada y además puede empujar contra los límites de
 * slowapi del backend (5/min en análisis y detalle, 10/min en propuesta), así
 * que solo se reintentan los fallos de red y los 5xx.
 */
function debeReintentar(intentos: number, error: unknown): boolean {
  if (intentos >= 2) return false;
  if (error instanceof ApiError) return error.status === 0 || error.status >= 500;
  return false;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: debeReintentar,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});
