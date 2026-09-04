import { enviarFormulario, pedir, segmento } from '@/lib/http';
import type { CargaResponse, PlanCuentasResponse, StatusResponse } from '@/types/api';

const base = (ruc: string) => `/empresas/${segmento(ruc)}/plan-cuentas`;

export interface FiltroCuentas {
  /** Filtra por código y por descripción a la vez, sin distinguir mayúsculas. */
  busqueda?: string;
  limit?: number;
  skip?: number;
}

export function listarCuentas(
  ruc: string,
  filtro: FiltroCuentas = {},
): Promise<PlanCuentasResponse> {
  return pedir<PlanCuentasResponse>(base(ruc), {
    consulta: {
      busqueda: filtro.busqueda,
      limit: filtro.limit ?? 100,
      skip: filtro.skip ?? 0,
    },
  });
}

/**
 * Sube el `.xlsx` que exporta Contasis. **Reemplaza el maestro completo**: el
 * archivo es la fuente de verdad, así que una cuenta que dejó de exportarse es
 * una cuenta que ya no existe. Límite 5/min.
 */
export function cargarCuentas(ruc: string, archivo: File): Promise<CargaResponse> {
  const datos = new FormData();
  datos.append('archivo', archivo);
  return enviarFormulario<CargaResponse>(base(ruc), datos);
}

export function eliminarCuentas(ruc: string): Promise<StatusResponse<{ cuentas: number }>> {
  return pedir<StatusResponse<{ cuentas: number }>>(base(ruc), { metodo: 'DELETE' });
}
