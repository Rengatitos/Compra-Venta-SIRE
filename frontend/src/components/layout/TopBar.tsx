import { NotificacionesMenu } from '@/features/jobs/NotificacionesMenu';

import { MenuLateralMovil } from './MenuLateralMovil';
import estilos from './TopBar.module.css';

/**
 * La marca, la empresa, el tema y la sesión se mudaron a la barra lateral. Aquí
 * queda lo que no es de una sección concreta: el botón que abre el cajón en
 * móvil y la campana de los trabajos en segundo plano, que se consulta desde
 * cualquier pantalla.
 */
export function TopBar() {
  return (
    <div className={estilos.barra}>
      <MenuLateralMovil />
      <div className={estilos.acciones}>
        <NotificacionesMenu />
      </div>
    </div>
  );
}
