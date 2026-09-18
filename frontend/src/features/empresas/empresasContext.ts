import { createContext } from 'react';

import type { EmpresaResponse } from '@/types/api';

export interface ContextoEmpresas {
  /** Todas las empresas registradas, ordenadas para el selector. */
  empresas: readonly EmpresaResponse[];
  /** RUC de la empresa activa. Dentro del panel nunca es null. */
  ruc: string | null;
  empresaActiva: EmpresaResponse | null;
  cambiarEmpresa: (ruc: string) => void;
  /** Tras dar de alta o eliminar una empresa. */
  recargar: () => void;
}

export const ContextoEmpresasReact = createContext<ContextoEmpresas | null>(null);
