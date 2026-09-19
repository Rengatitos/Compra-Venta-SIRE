import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router';

import { iniciarSesionConGoogle as entrarConGoogle } from '@/api/auth';
import { olvidarSeleccionGoogle } from '@/lib/google';
import { useToast } from '@/hooks/useToast';
import { registrarManejadorDeSesionExpirada } from '@/lib/http';
import { guardarSesion, limpiarSesion, obtenerSesion, suscribirSesion } from '@/lib/session';

import { ContextoAuthReact } from './authContext';

/**
 * Identidad de la persona. La empresa sobre la que se trabaja vive aparte, en
 * `features/empresas`: son dos ciclos de vida distintos y el de la empresa
 * necesita una consulta que no debe dispararse en la pantalla de acceso.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const navegar = useNavigate();
  const cliente = useQueryClient();

  const { mostrar } = useToast();

  const sesion = useSyncExternalStore(suscribirSesion, obtenerSesion, () => null);

  const salir = useCallback(() => {
    limpiarSesion();
    // Sin esto Google volvería a entrar sola con la última cuenta usada.
    olvidarSeleccionGoogle();
    cliente.clear();
    void navegar('/login', { replace: true });
  }, [cliente, navegar]);

  /**
   * El JWT dura 2 h (`JWT_EXPIRE_HOURS`), así que caducar en pantalla es el caso
   * normal. La capa HTTP avisa aquí y se sale de la sesión con un mensaje, en
   * lugar de dejar la interfaz llena de errores 401.
   *
   * El aviso sale por un toast, que es el canal de todo el panel. Para que no
   * se apile con otro mensaje del mismo suceso, la capa HTTP solo llama aquí
   * cuando de verdad había una sesión: un 401 de `POST /auth/google` es un
   * intento de entrar rechazado, no una caducidad.
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

  const iniciarSesionConGoogle = useCallback(async (idToken: string) => {
    const respuesta = await entrarConGoogle(idToken);
    guardarSesion({
      token: respuesta.access_token,
      correo: respuesta.usuario.email,
      nombre: respuesta.usuario.nombre ?? undefined,
      // Todavía sin empresa: la elige `EmpresaGate` con la lista del backend.
      ruc: null,
    });
  }, []);

  const valor = useMemo(
    () => ({
      correo: sesion?.correo ?? null,
      nombre: sesion?.nombre ?? null,
      autenticado: sesion !== null,
      iniciarSesionConGoogle,
      salir,
    }),
    [sesion, iniciarSesionConGoogle, salir],
  );

  return <ContextoAuthReact.Provider value={valor}>{children}</ContextoAuthReact.Provider>;
}
