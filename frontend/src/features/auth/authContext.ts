import { createContext } from 'react';

import type { EmpresaLogin } from '@/types/api';

export interface ContextoAuth {
  /** RUC de la empresa autenticada, o null si no hay sesión. */
  ruc: string | null;
  autenticado: boolean;
  iniciarSesion: (credenciales: EmpresaLogin) => Promise<void>;
  salir: () => void;
}

export const ContextoAuthReact = createContext<ContextoAuth | null>(null);
