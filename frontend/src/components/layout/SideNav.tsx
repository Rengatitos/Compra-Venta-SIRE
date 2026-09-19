import { Link } from 'react-router';

import { SelectorEmpresa } from '@/features/empresas/SelectorEmpresa';
import { NotificacionesMenu } from '@/features/jobs/NotificacionesMenu';

import { construirNavegacion } from './navegacion';
import { NavEnlace } from './NavEnlace';
import { NavGrupo } from './NavGrupo';
import estilos from './SideNav.module.css';
import { SideNavCuenta } from './SideNavCuenta';
import { usePeriodoActivo } from './usePeriodoActivo';

interface Props {
  /** El cajón de móvil se cierra al navegar. En escritorio no se pasa nada. */
  onNavegar?: () => void;
}

/**
 * Contenido de la barra lateral: marca y empresa arriba, secciones en medio y
 * la zona de cuenta abajo. Se monta igual en la columna fija de escritorio y
 * dentro del cajón de móvil.
 */
export function SideNav({ onNavegar }: Props) {
  const periodo = usePeriodoActivo();
  const entradas = construirNavegacion(periodo);

  return (
    <div className={estilos.panel}>
      <div className={estilos.encabezado}>
        <div className={estilos.filaMarca}>
          <Link className={estilos.marca} to="/" onClick={onNavegar}>
            <span className={estilos.monograma} aria-hidden="true">
              SI
            </span>
            <span className={estilos.textosMarca}>
              <span className={estilos.nombre}>SIRE</span>
              <span className={estilos.subtitulo}>Registro de compras electrónico</span>
            </span>
          </Link>

          {/* En móvil la campana vive en la cabecera, que es lo que se ve con el
              cajón cerrado; aquí se oculta para no duplicarla. */}
          <div className={estilos.campana}>
            <NotificacionesMenu alineacion="inicio" />
          </div>
        </div>

        <SelectorEmpresa bloque />
      </div>

      {/* Lo único que se desplaza: el encabezado y la zona de cuenta quedan
          siempre a la vista, por larga que se ponga la lista. */}
      <div className={estilos.cuerpo}>
        <nav aria-label="Secciones de la aplicación">
          <p className={estilos.grupo}>General</p>
          <ul className={estilos.lista}>
            {entradas.map((entrada) =>
              entrada.hijos ? (
                <NavGrupo
                  key={entrada.a}
                  entrada={{ ...entrada, hijos: entrada.hijos }}
                  onNavegar={onNavegar}
                />
              ) : (
                <NavEnlace key={entrada.a} entrada={entrada} onNavegar={onNavegar} />
              ),
            )}
          </ul>
        </nav>
      </div>

      <SideNavCuenta onNavegar={onNavegar} />
    </div>
  );
}
