import { Link } from 'react-router';

import estilos from './SideNav.module.css';

interface Props {
  onNavegar?: () => void;
}

/**
 * Marca de la barra lateral del panel general. Lleva a la raíz, que es el
 * panel de todas las empresas.
 */
export function SideNavMarca({ onNavegar }: Props) {
  return (
    <Link className={estilos.marca} to="/" onClick={onNavegar}>
      <span className={estilos.monograma} aria-hidden="true">
        SI
      </span>
      <span className={estilos.textosMarca}>
        <span className={estilos.nombre}>SIRE</span>
        <span className={estilos.subtitulo}>Registro de compras electrónico</span>
      </span>
    </Link>
  );
}
