import { useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router';

import { IconoCerrar, IconoMenu } from './IconosNav';
import estilos from './MenuLateralMovil.module.css';
import { SideNav } from './SideNav';

interface Props {
  /** Barra que se monta en el cajón. Por defecto, la de la empresa activa. */
  barra?: (onNavegar: () => void) => ReactNode;
}

/**
 * En móvil la barra lateral se sirve como cajón.
 *
 * Es un `<dialog>` nativo, así que el atrapado de foco, Escape, la devolución
 * del foco al botón y la capa superior los pone el navegador. No se reutiliza
 * el componente `Dialog` porque impone encabezado, cuerpo y fila de acciones
 * centrados, que es justo lo contrario de un panel pegado al borde.
 */
export function MenuLateralMovil({ barra }: Props) {
  const [abierto, setAbierto] = useState(false);
  const referencia = useRef<HTMLDialogElement>(null);
  const idCajon = useId();
  const ubicacion = useLocation();

  useEffect(() => {
    const elemento = referencia.current;
    if (!elemento) return;

    if (abierto && !elemento.open) elemento.showModal();
    if (!abierto && elemento.open) elemento.close();
  }, [abierto]);

  useEffect(() => {
    const elemento = referencia.current;
    if (!elemento) return;

    const alCancelar = (evento: Event) => {
      evento.preventDefault();
      setAbierto(false);
    };

    // Clic fuera: en un diálogo modal el fondo es el propio `::backdrop`, así
    // que el objetivo del clic es el diálogo y no su contenido. Va como
    // listener nativo y no como `onClick` en el JSX porque ahí `jsx-a11y` lo
    // lee como un elemento no interactivo con manejador de ratón.
    const alPulsar = (evento: MouseEvent) => {
      if (evento.target === elemento) setAbierto(false);
    };

    elemento.addEventListener('cancel', alCancelar);
    elemento.addEventListener('click', alPulsar);
    return () => {
      elemento.removeEventListener('cancel', alCancelar);
      elemento.removeEventListener('click', alPulsar);
    };
  }, []);

  // Red de seguridad para las navegaciones que no salen de un enlace del cajón,
  // como cambiar de empresa desde el selector.
  useEffect(() => {
    setAbierto(false);
  }, [ubicacion.pathname]);

  return (
    <>
      <button
        type="button"
        className={estilos.boton}
        aria-label="Abrir el menú de navegación"
        aria-haspopup="dialog"
        aria-expanded={abierto}
        aria-controls={idCajon}
        onClick={() => setAbierto(true)}
      >
        <IconoMenu />
      </button>

      <dialog ref={referencia} id={idCajon} className={estilos.cajon} aria-label="Navegación">
        <button
          type="button"
          className={estilos.cerrar}
          aria-label="Cerrar el menú de navegación"
          onClick={() => setAbierto(false)}
        >
          <IconoCerrar />
        </button>

        {/* Solo se monta abierto: así no hay dos árboles de navegación vivos a
            la vez. */}
        {abierto ? (
          barra ? (
            barra(() => setAbierto(false))
          ) : (
            <SideNav onNavegar={() => setAbierto(false)} />
          )
        ) : null}
      </dialog>
    </>
  );
}
