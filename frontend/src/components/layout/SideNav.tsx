import { ButtonLink } from '@/components/ui/Button';

import { construirNavegacion } from './navegacion';
import { NavEnlace } from './NavEnlace';
import { NavGrupo } from './NavGrupo';
import estilos from './SideNav.module.css';
import { usePeriodoActivo } from './usePeriodoActivo';

interface Props {
  /** El cajón de móvil se cierra al navegar. En escritorio no se pasa nada. */
  onNavegar?: () => void;
}

/**
 * Barra lateral de una empresa: solo sus secciones y, abajo, la vuelta al panel
 * de todas para escoger otra. La marca, el tema y la sesión viven en la barra
 * del panel general. Se monta igual en la columna fija de escritorio y dentro
 * del cajón de móvil.
 */
export function SideNav({ onNavegar }: Props) {
  const periodo = usePeriodoActivo();
  const entradas = construirNavegacion(periodo);

  return (
    <div className={estilos.panel}>
      {/* Lo único que se desplaza: la vuelta a las empresas queda siempre a la
          vista, por larga que se ponga la lista. */}
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

      <div className={estilos.pie}>
        <ButtonLink a="/" variante="secundario" bloque onClick={onNavegar}>
          Volver a las empresas
        </ButtonLink>
      </div>
    </div>
  );
}
