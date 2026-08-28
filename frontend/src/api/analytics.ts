import { pedir } from '@/lib/http';
import type { DashboardData } from '@/types/api';
import type { Libro } from '@/types/domain';

/**
 * Los endpoints de analytics están pensados para consultar varias empresas a la
 * vez, así que el RUC va en `rucs` (lista separada por comas). Sin `rucs` el
 * filtro queda vacío y las agregaciones no devuelven nada, de modo que este
 * frontend siempre envía el RUC de la sesión.
 */
export function obtenerDashboard(
  rucs: readonly string[],
  periodo: string,
  libro: Libro,
): Promise<DashboardData> {
  return pedir<DashboardData>('/analytics/dashboard-data', {
    consulta: { rucs: rucs.join(','), periodo, libro },
  });
}

/** Periodos que ya tienen comprobantes cargados, para el selector. */
export function obtenerPeriodosConDatos(rucs: readonly string[]): Promise<string[]> {
  return pedir<string[]>('/analytics/periodos', { consulta: { rucs: rucs.join(',') } });
}
