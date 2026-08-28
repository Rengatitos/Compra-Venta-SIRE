import { Navigate, Outlet, useLocation } from 'react-router';

import { useAuth } from './useAuth';

/**
 * Guarda de sesión. Recuerda a dónde iba el usuario para devolverlo ahí después
 * de iniciar sesión.
 */
export function ProtectedRoute() {
  const { autenticado } = useAuth();
  const ubicacion = useLocation();

  if (!autenticado) {
    return <Navigate to="/login" replace state={{ desde: ubicacion.pathname }} />;
  }

  return <Outlet />;
}
