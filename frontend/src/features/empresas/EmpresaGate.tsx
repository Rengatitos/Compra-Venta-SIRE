import { useQuery } from '@tanstack/react-query';
import { useCallback, useMemo, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { Outlet, useNavigate } from 'react-router';

import { listarEmpresas } from '@/api/empresas';
import { Button } from '@/components/ui/Button';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { useAuth } from '@/features/auth/useAuth';
import { useToast } from '@/hooks/useToast';
import { guardarEmpresaActiva, obtenerSesion, suscribirSesion } from '@/lib/session';
import type { EmpresaResponse } from '@/types/api';

import { ContextoEmpresasReact } from './empresasContext';
import { FormularioNuevaEmpresa } from './FormularioNuevaEmpresa';
import { ListaEmpresas } from './ListaEmpresas';
import { Marco } from './Marco';
import estilos from './Marco.module.css';

/** El marco común, con lo que este paso tiene que decir y ofrecer. */
function MarcoDelGate({ titulo, children }: { titulo: string; children: ReactNode }) {
  const { correo, salir } = useAuth();

  return (
    <Marco
      titulo={titulo}
      intro={
        <>
          Has entrado como <strong>{correo}</strong>.
        </>
      }
      pie={
        <Button variante="fantasma" pequeno onClick={salir}>
          Cerrar sesión
        </Button>
      }
    >
      {children}
    </Marco>
  );
}

/**
 * Elige la empresa sobre la que se trabaja y la ofrece al resto del panel.
 *
 * Va entre `ProtectedRoute` (que exige sesión, porque este componente ya pide
 * datos al backend) y `AppShell` (que exige empresa activa). Es la pieza que
 * sustituye a lo que antes hacía el login: allí la empresa venía de las
 * credenciales con las que entrabas y aquí se elige, que es justo lo que
 * permite cambiar de cuenta sin volver a autenticarse.
 */
export function EmpresaGate() {
  const navegar = useNavigate();
  const { mostrar } = useToast();

  const sesion = useSyncExternalStore(suscribirSesion, obtenerSesion, () => null);
  const guardado = sesion?.ruc ?? null;

  const consulta = useQuery({
    queryKey: ['empresas'],
    queryFn: listarEmpresas,
    staleTime: 5 * 60_000,
  });

  const empresas = useMemo(
    () => [...(consulta.data ?? [])].sort((a, b) => a.ruc.localeCompare(b.ruc)),
    [consulta.data],
  );

  // El RUC guardado se valida siempre contra la lista: una empresa eliminada
  // desde otra sesión dejaría el panel en un 404 permanente.
  const activo = useMemo(() => {
    if (guardado && empresas.some((empresa) => empresa.ruc === guardado)) return guardado;
    // Con una sola empresa no tiene sentido preguntar cuál.
    if (empresas.length === 1) return empresas[0]?.ruc ?? null;
    return null;
  }, [guardado, empresas]);

  const cambiarEmpresa = useCallback(
    (nuevo: string) => {
      if (nuevo === activo) return;
      guardarEmpresaActiva(nuevo);
      // Las claves de React Query llevan el RUC, así que el caché se re-keya
      // solo y no hace falta vaciarlo. Lo que sí hace falta es salir de la ruta
      // actual: `/periodos/202607` puede no existir en la empresa nueva, y el
      // `?comprobante=` de la anterior tampoco.
      void navegar('/', { replace: true });
    },
    [activo, navegar],
  );

  const alCrear = useCallback(
    (empresa: EmpresaResponse) => {
      guardarEmpresaActiva(empresa.ruc);
      void consulta.refetch();
      mostrar({ tono: 'exito', titulo: 'Empresa registrada' });
      void navegar('/', { replace: true });
    },
    [consulta, mostrar, navegar],
  );

  const valor = useMemo(
    () => ({
      empresas,
      ruc: activo,
      empresaActiva: empresas.find((empresa) => empresa.ruc === activo) ?? null,
      cambiarEmpresa,
      recargar: () => void consulta.refetch(),
    }),
    [empresas, activo, cambiarEmpresa, consulta],
  );

  if (consulta.isPending) {
    return (
      <MarcoDelGate titulo="Cargando tus empresas">
        <Skeleton lineas={3} etiqueta="Cargando las empresas" />
      </MarcoDelGate>
    );
  }

  if (consulta.isError) {
    return (
      <MarcoDelGate titulo="No se pudieron cargar las empresas">
        <ErrorState
          titulo="Error al consultar el servidor"
          texto="Revisa tu conexión y vuelve a intentarlo."
          accion={
            <Button variante="primario" onClick={() => void consulta.refetch()}>
              Reintentar
            </Button>
          }
        />
      </MarcoDelGate>
    );
  }

  if (empresas.length === 0) {
    // Antes este estado era inalcanzable: se entraba con las credenciales de una
    // empresa que por definición existía. Ahora es el primer arranque en limpio,
    // y el formulario va incrustado porque `/empresas/nueva` vive dentro del
    // panel, que a su vez exige una empresa activa.
    return (
      <MarcoDelGate titulo="Todavía no hay ninguna empresa">
        <p className={estilos.intro}>
          La base de datos no tiene ninguna empresa registrada. Da de alta la primera con su RUC y
          sus credenciales SOL para empezar a sincronizar el SIRE.
        </p>
        <FormularioNuevaEmpresa onCreada={alCrear} />
      </MarcoDelGate>
    );
  }

  if (!activo) {
    return (
      <MarcoDelGate titulo="Elige una empresa">
        <p className={estilos.intro}>
          Podrás cambiar de empresa en cualquier momento desde la barra lateral, sin volver a
          iniciar sesión.
        </p>
        <ListaEmpresas empresas={empresas} onElegir={(elegido) => guardarEmpresaActiva(elegido)} />
      </MarcoDelGate>
    );
  }

  return (
    <ContextoEmpresasReact.Provider value={valor}>
      <Outlet />
    </ContextoEmpresasReact.Provider>
  );
}
