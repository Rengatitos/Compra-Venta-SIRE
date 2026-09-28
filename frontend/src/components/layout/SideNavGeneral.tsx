import { IconoPanel } from './IconosNav';
import { construirNavegacionGeneral } from './navegacion';
import { NavEnlace } from './NavEnlace';
import estilos from './SideNav.module.css';
import { SideNavCuenta } from './SideNavCuenta';
import { SideNavMarca } from './SideNavMarca';

interface Props {
  /** Nombre (o RUC) de la empresa recordada, para ofrecer volver a su panel. */
  empresaActiva?: string | null;
  onNavegar?: () => void;
}

/**
 * Barra lateral del panel de todas las empresas: marca, secciones y cuenta. Es
 * el único sitio con el tema y el cierre de sesión; la de una empresa solo
 * lleva sus secciones y la vuelta hasta aquí. Tampoco hay campana: sigue los
 * procesos de una sola empresa.
 */
export function SideNavGeneral({ empresaActiva, onNavegar }: Props) {
  return (
    <div className={estilos.panel}>
      <div className={estilos.encabezado}>
        <div className={estilos.filaMarca}>
          <SideNavMarca onNavegar={onNavegar} />
        </div>
      </div>

      <div className={estilos.cuerpo}>
        <nav aria-label="Secciones de la aplicación">
          <p className={estilos.grupo}>Todas las empresas</p>
          <ul className={estilos.lista}>
            {construirNavegacionGeneral().map((entrada) => (
              <NavEnlace key={entrada.a} entrada={entrada} onNavegar={onNavegar} />
            ))}
          </ul>

          {empresaActiva ? (
            <>
              <p className={estilos.grupo}>Empresa activa</p>
              <ul className={estilos.lista}>
                <NavEnlace
                  entrada={{ a: '/dashboard', texto: empresaActiva, icono: IconoPanel }}
                  onNavegar={onNavegar}
                />
              </ul>
            </>
          ) : null}
        </nav>
      </div>

      <SideNavCuenta onNavegar={onNavegar} />
    </div>
  );
}
