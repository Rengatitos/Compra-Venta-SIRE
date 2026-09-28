import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import { obtenerResumenEmpresas } from '@/api/empresas';

const INTERVALO_MS = 5000;

/**
 * Resumen de todas las empresas. Lo piden varias pantallas del panel general y
 * su barra lateral; React Query sirve a todas con una sola consulta.
 */
export function useResumenEmpresas() {
  const resumen = useQuery({
    queryKey: ['resumen-empresas'],
    queryFn: obtenerResumenEmpresas,
    // Mientras haya procesos vivos el panel se refresca solo; después, no.
    refetchInterval: (consulta) => {
      const vivos = consulta.state.data?.procesos_por_estado;
      return vivos && vivos.pendiente + vivos.en_progreso > 0 ? INTERVALO_MS : false;
    },
  });

  const empresas = useMemo(() => resumen.data?.empresas ?? [], [resumen.data]);
  /** RUC → nombre, o el RUC si no tiene razón social. */
  const nombres = useMemo(
    () => new Map(empresas.map((e) => [e.ruc, e.nombre ?? e.ruc] as const)),
    [empresas],
  );

  return { resumen, empresas, nombres };
}
