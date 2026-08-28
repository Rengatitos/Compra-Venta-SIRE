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
  children?: ReactNode;
}

/**
 * Diálogo modal sobre `<dialog>` nativo: el navegador aporta el atrapado de
 * foco, el cierre con Escape, `aria-modal` y la devolución del foco al elemento
 * que lo abrió. No hace falta reimplementar nada de eso.
 */
export function Dialog({ abierto, titulo, texto, onCerrar, acciones, children }: Props) {
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
      className={estilos.dialogo}
      aria-labelledby={idTitulo}
      aria-describedby={texto ? idTexto : undefined}
    >
      <div className={estilos.contenido}>
        <h2 className={estilos.titulo} id={idTitulo}>
          {titulo}
        </h2>
        {texto ? (
          <p className={estilos.texto} id={idTexto}>
            {texto}
          </p>
        ) : null}
        {children}
        <div className={estilos.acciones}>{acciones}</div>
      </div>
    </dialog>
  );
}
