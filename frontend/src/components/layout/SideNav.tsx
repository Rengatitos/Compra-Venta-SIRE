import { NavLink } from 'react-router';

import estilos from './SideNav.module.css';

interface Entrada {
  a: string;
  texto: string;
  /** `end` para que "/" no quede activo en todas las rutas hijas. */
  exacto?: boolean;
}

const ENTRADAS: readonly Entrada[] = [
  { a: '/', texto: 'Dashboard', exacto: true },
  { a: '/periodos', texto: 'Periodos' },
  { a: '/referencias', texto: 'Referencias' },
  { a: '/ajustes', texto: 'Ajustes' },
];

export function SideNav() {
  return (
    <>
      <p className={estilos.grupo}>Navegación</p>
      <ul className={estilos.lista}>
        {ENTRADAS.map((entrada) => (
          <li key={entrada.a}>
            <NavLink
              to={entrada.a}
              end={entrada.exacto}
              className={({ isActive }) =>
                `${estilos.enlace} ${isActive ? (estilos.activo ?? '') : ''}`
              }
            >
              {entrada.texto}
            </NavLink>
          </li>
        ))}
      </ul>
    </>
  );
}
