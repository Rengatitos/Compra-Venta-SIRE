import { useId, useState } from 'react';
import { NavLink, useMatch } from 'react-router';

import { clases } from './clases';
import { IconoChevron } from './IconosNav';
import type { Entrada, SubEntrada } from './navegacion';
import { NavEnlace } from './NavEnlace';
import estilos from './SideNav.module.css';

interface Props {
  entrada: Entrada & { hijos: readonly SubEntrada[] };
  onNavegar?: () => void;
}

/**
 * Ítem de navegación con segundo nivel. El chevron es un botón de despliegue y
 * el resto de la fila sigue siendo el enlace a la sección: así no se pierde ni
 * el acceso a `/periodos` ni el control del desplegable, y no queda un botón
 * dentro de un enlace.
 */
export function NavGrupo({ entrada, onNavegar }: Props) {
  const idLista = useId();
  const dentro = useMatch(`${entrada.a}/*`) !== null;
  const Icono = entrada.icono;

  // Se abre solo al entrar en la sección y se puede cerrar a mano; al cambiar de
  // sección vuelve a mandar la ruta. Ajustar el estado durante el render es lo
  // que recomienda React para esto: con un efecto se pintaría un fotograma con
  // el valor viejo.
  const [previo, setPrevio] = useState(dentro);
  const [abierto, setAbierto] = useState(dentro);
  if (previo !== dentro) {
    setPrevio(dentro);
    setAbierto(dentro);
  }

  return (
    <li className={estilos.item}>
      <div className={clases(estilos.fila, dentro && estilos.enSeccion)}>
        <NavLink
          to={entrada.a}
          end={entrada.exacto}
          onClick={onNavegar}
          className={({ isActive }) => clases(estilos.enlace, isActive && estilos.activo)}
        >
          <Icono />
          <span className={estilos.texto}>{entrada.texto}</span>
        </NavLink>

        {/* El chevron va al final y no al principio: delante obligaría a sangrar
            todas las demás filas su mismo ancho para que los iconos siguieran
            en columna, y entonces la lista no cuadraría con su rótulo. */}
        <button
          type="button"
          className={clases(estilos.disparador, abierto && estilos.desplegado)}
          aria-expanded={abierto}
          aria-controls={idLista}
          aria-label={`${abierto ? 'Contraer' : 'Desplegar'} ${entrada.texto}`}
          onClick={() => setAbierto((valor) => !valor)}
        >
          <IconoChevron />
        </button>
      </div>

      {/* `hidden` en vez de render condicional: así `aria-controls` siempre
          apunta a un elemento que existe. */}
      <ul className={estilos.sublista} id={idLista} hidden={!abierto}>
        {entrada.hijos.map((hijo) => (
          <NavEnlace key={hijo.a} entrada={hijo} onNavegar={onNavegar} />
        ))}
      </ul>
    </li>
  );
}
