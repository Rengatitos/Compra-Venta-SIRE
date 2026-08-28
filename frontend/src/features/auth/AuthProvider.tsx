import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';

import { login } from '@/api/auth';
import { useToast } from '@/hooks/useToast';
import { registrarManejadorDeSesionExpirada } from '@/lib/http';
import { guardarSesion, limpiarSesion, obtenerSesion, suscribirSesion } from '@/lib/session';
import type { EmpresaLogin } from '@/types/api';

import { ContextoAuthReact } from './authContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const navegar = useNavigate();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const sesion = useSyncExternalStore(suscribirSesion, obtenerSesion, () => null);

  const salir = useCallback(() => {
    limpiarSesion();
    cliente.clear();
    void navegar('/login', { replace: true });
  }, [cliente, navegar]);

  /**
   * El JWT dura 2 h (`JWT_EXPIRE_HOURS`), así que caducar en pantalla es el caso
   * normal. La capa HTTP avisa aquí y se sale de la sesión con un mensaje, en
   * lugar de dejar la interfaz llena de errores 401.
   */
  useEffect(() => {
    registrarManejadorDeSesionExpirada(() => {
      cliente.clear();
      mostrar({
        tono: 'error',
        titulo: 'Sesión expirada',
        detalle: 'Vuelve a iniciar sesión para continuar.',
      });
      void navegar('/login', { replace: true });
    });
    return () => {
      registrarManejadorDeSesionExpirada(null);
    };
  }, [cliente, mostrar, navegar]);

  const iniciarSesion = useCallback(async (credenciales: EmpresaLogin) => {
    const respuesta = await login(credenciales);
    guardarSesion({ token: respuesta.access_token, ruc: credenciales.ruc });
  }, []);

  const valor = useMemo(
    () => ({
      ruc: sesion?.ruc ?? null,
      autenticado: sesion !== null,
      iniciarSesion,
      salir,
    }),
    [sesion, iniciarSesion, salir],
  );

  return <ContextoAuthReact.Provider value={valor}>{children}</ContextoAuthReact.Provider>;
}
