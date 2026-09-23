import { useQuery } from '@tanstack/react-query';

import { obtenerYo } from '@/api/usuarios';

/** Si la sesión es de un administrador. El rol lo decide el backend en cada consulta. */
export function useEsAdmin(): boolean {
  const yo = useQuery({ queryKey: ['yo'], queryFn: obtenerYo, staleTime: 60_000 });
  return yo.data?.rol === 'admin';
}
