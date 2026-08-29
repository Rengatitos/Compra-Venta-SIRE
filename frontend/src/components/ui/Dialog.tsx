import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';

import estilos from './Dialog.module.css';

interface Props {
  abierto: boolean;
  titulo: string;
  texto?: string;
  /** Se dispara al pulsar Escape, al cerrar con el backdrop o desde las acciones. */
  onCerrar: () => void;
  acciones: ReactNode;
  /** `amplio` para contenido con tablas; el ancho normal es de lectura. */
  ancho?: 'normal' | 'amplio';
  children?: ReactNode;
}

/**
 * Diálogo modal sobre `<dialog>` nativo: el atrapado de foco, el cierre con
 * Escape, `aria-modal` y la devolución del foco al elemento que lo abrió los
 * aporta el navegador. No hace falta reimplementar nada de eso.
 *
 * El cuerpo se desplaza por su cuenta y el encabezado y las acciones quedan
 * fijos, así que un contenido largo no deja el botón de cerrar fuera de vista.
 */
export function Dialog({
  abierto,
  titulo,
  texto,
  onCerrar,
  acciones,
  ancho = 'normal',
  children,
}: Props) {
  const referencia = useRef<HTMLDialogElement>(null);
  const idTitulo = useId();
  const idTexto = useId();

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
      onCerrar();
    };
    elemento.addEventListener('cancel', alCancelar);
    return () => {
      elemento.removeEventListener('cancel', alCancelar);
    };
  }, [onCerrar]);

  return (
    <dialog
      ref={referencia}
      className={`${estilos.dialogo} ${ancho === 'amplio' ? (estilos.amplio ?? '') : ''}`}
      aria-labelledby={idTitulo}
      aria-describedby={texto ? idTexto : undefined}
    >
      <div className={estilos.cabecera}>
        <h2 className={estilos.titulo} id={idTitulo}>
          {titulo}
        </h2>
        {texto ? (
          <p className={estilos.texto} id={idTexto}>
            {texto}
          </p>
        ) : null}
      </div>

      {children ? <div className={estilos.cuerpo}>{children}</div> : null}

      <div className={estilos.acciones}>{acciones}</div>
    </dialog>
  );
}
