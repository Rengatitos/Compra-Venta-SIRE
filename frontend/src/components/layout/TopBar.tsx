import type { ReactNode } from 'react';

import { NotificacionesMenu } from '@/features/jobs/NotificacionesMenu';

import { MenuLateralMovil } from './MenuLateralMovil';
import estilos from './TopBar.module.css';

interface Props {
  /** Qué barra monta el cajón. Por defecto, la de la empresa activa. */
  barra?: (onNavegar: () => void) => ReactNode;
  /** La campana sigue los procesos de una empresa: fuera de una, no va. */
  campana?: boolean;
}

/**
 * La marca, la empresa, el tema y la sesión se mudaron a la barra lateral. Aquí
 * queda lo que no es de una sección concreta: el botón que abre el cajón en
 * móvil y la campana de los trabajos en segundo plano, que se consulta desde
 * cualquier pantalla.
 */
export function TopBar({ barra, campana = true }: Props) {
  return (
    <div className={estilos.barra}>
      <MenuLateralMovil barra={barra} />
      {campana ? (
        <div className={estilos.acciones}>
          <NotificacionesMenu />
        </div>
      ) : null}
    </div>
  );
}
