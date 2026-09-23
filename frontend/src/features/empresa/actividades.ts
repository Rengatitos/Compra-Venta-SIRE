import type { EmpresaResponse } from '@/types/api';

/** Ancla del panel de actividades en Ajustes; a ella lleva el «editar» del Dashboard. */
export const ANCLA_ACTIVIDADES = 'actividades';

/** La actividad que manda al clasificar: la elegida o, sin elección, la principal de SUNAT. */
export function principalEfectiva(empresa: EmpresaResponse | undefined): string | null {
  const actividades = empresa?.actividades_economicas ?? [];
  const elegida = empresa?.ciiu_principal_clasificacion;
  if (elegida && actividades.some((a) => a.ciiu === elegida)) return elegida;
  return actividades.find((a) => a.tipo === 'PRINCIPAL')?.ciiu ?? actividades[0]?.ciiu ?? null;
}
