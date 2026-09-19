import { NavLink } from 'react-router';

import { clases } from './clases';
import type { Entrada, SubEntrada } from './navegacion';
import estilos from './SideNav.module.css';

interface Props {
  entrada: Entrada | SubEntrada;
  onNavegar?: () => void;
}

/**
 * Fila de navegación sin segundo nivel. Sirve igual en la raíz y en el segundo
 * nivel: la sangría de los hijos la pone su lista, no el enlace.
 */
export function NavEnlace({ entrada, onNavegar }: Props) {
  const Icono = entrada.icono;

  return (
    <li>
      <NavLink
        to={entrada.a}
        end={entrada.exacto}
        onClick={onNavegar}
        className={({ isActive }) =>
          clases(estilos.enlace, isActive && estilos.activo)
        }
      >
        <Icono />
        <span className={estilos.texto}>{entrada.texto}</span>
      </NavLink>
    </li>
  );
}
