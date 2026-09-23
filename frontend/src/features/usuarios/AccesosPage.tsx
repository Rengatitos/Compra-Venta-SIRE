import { useQuery } from '@tanstack/react-query';

import { obtenerYo } from '@/api/usuarios';
import { ButtonLink } from '@/components/ui/Button';
import { EmptyState, Skeleton } from '@/components/ui/Feedback';
import { Marco } from '@/features/empresas/Marco';

import { GestionAccesos } from './GestionAccesos';

/**
 * Quién puede entrar al panel, en una pantalla propia y fuera del armazón: no
 * depende de ninguna empresa, así que va con el mismo marco que la elección de
 * empresa, desde donde se llega con el botón de arriba.
 */
export function AccesosPage() {
  const yo = useQuery({ queryKey: ['yo'], queryFn: obtenerYo, staleTime: 60_000 });

  return (
    <Marco
      titulo="Cuentas con acceso"
      intro="Correos de Google que pueden entrar. Los administradores también dan y quitan accesos; los usuarios solo trabajan con las empresas."
      pie={
        <ButtonLink a="/" variante="fantasma" pequeno>
          Volver
        </ButtonLink>
      }
    >
      {yo.isPending ? <Skeleton lineas={3} etiqueta="Comprobando tu rol" /> : null}
      {yo.data && yo.data.rol !== 'admin' ? (
        <EmptyState
          titulo="Solo para administradores"
          texto="Pide a un administrador que te dé acceso o que cambie tu rol."
        />
      ) : null}
      {yo.data?.rol === 'admin' ? <GestionAccesos independiente /> : null}
    </Marco>
  );
}
