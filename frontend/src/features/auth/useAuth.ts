import { useContext } from 'react';

import { ContextoAuthReact } from './authContext';
import type { ContextoAuth } from './authContext';

export function useAuth(): ContextoAuth {
  const contexto = useContext(ContextoAuthReact);
  if (!contexto) {
    throw new Error('useAuth necesita estar dentro de <AuthProvider>.');
  }
  return contexto;
}

/**
 * Sigue siendo el único punto del que las pantallas obtienen el RUC activo, y
 * mantiene su contrato: devuelve el RUC o lanza. Lo que cambió es de dónde sale.
 * Ya no viene de la sesión —una persona ve todas las empresas— sino de la
 * empresa elegida en el panel, que resuelve `EmpresaGate`. Se re-exporta desde
 * aquí para no tocar los imports de las pantallas que ya lo usaban.
 */
export { useRuc } from '@/features/empresas/useEmpresas';
