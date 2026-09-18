import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { useAuth } from '@/features/auth/useAuth';

import { IconoSalir } from './IconosNav';
import estilos from './SideNav.module.css';

interface Props {
  onNavegar?: () => void;
}

/**
 * Pie de la barra lateral: tema, cierre de sesión y quién está dentro. Vive
 * fuera del `<nav>` a propósito — no son secciones de la aplicación — pero
 * dentro del `<aside>`, que es el landmark que lo cubre.
 */
export function SideNavCuenta({ onNavegar }: Props) {
  const { correo, nombre, salir } = useAuth();
  const inicial = (nombre?.trim() || correo || '?').charAt(0).toUpperCase();

  return (
    <div className={estilos.cuenta}>
      <p className={estilos.grupo}>Cuenta</p>

      <ThemeToggle apariencia="fila" />

      {/* Una fila y no un `Button`: el primitivo centra su contenido, así que
          su icono no caería en la columna de los de la navegación. */}
      <button
        type="button"
        className={estilos.accion}
        onClick={() => {
          onNavegar?.();
          salir();
        }}
      >
        <IconoSalir />
        <span>Cerrar sesión</span>
      </button>

      <div className={estilos.usuario}>
        <span className={estilos.avatar} aria-hidden="true">
          {inicial}
        </span>
        <span className={estilos.datos}>
          <span className={estilos.nombreUsuario}>{nombre ?? 'Sesión activa'}</span>
          <span className={estilos.correo}>
            <span className="visually-hidden">Sesión de: </span>
            {correo}
          </span>
        </span>
      </div>
    </div>
  );
}
