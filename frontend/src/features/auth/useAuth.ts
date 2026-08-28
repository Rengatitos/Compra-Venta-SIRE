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
 * Para pantallas que ya están detrás de ProtectedRoute y por tanto siempre
 * tienen RUC. Evita comprobar null en cada componente.
 */
export function useRuc(): string {
  const { ruc } = useAuth();
  if (!ruc) {
    throw new Error('Se esperaba una sesión activa en esta ruta.');
  }
  return ruc;
}
