import { useEffect, useId, useRef } from 'react';
import type { InputHTMLAttributes } from 'react';

import estilos from './Checkbox.module.css';

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'className' | 'id'> & {
  etiqueta: string;
  /** La etiqueta se lee pero no se ve: para casillas dentro de una tabla. */
  etiquetaOculta?: boolean;
  /** Tercer estado del «seleccionar todas» cuando solo hay algunas marcadas. */
  indeterminado?: boolean;
  ayuda?: string;
};

/**
 * Casilla nativa con su `<label>`. `indeterminado` no existe como atributo
 * HTML, así que se fija en el elemento después de montarlo.
 */
export function Checkbox({ etiqueta, etiquetaOculta, indeterminado, ayuda, ...resto }: Props) {
  const base = useId();
  const control = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (control.current) control.current.indeterminate = Boolean(indeterminado);
  }, [indeterminado]);

  return (
    <div className={estilos.campo}>
      <input
        {...resto}
        ref={control}
        type="checkbox"
        id={`${base}-control`}
        className={estilos.casilla}
        aria-describedby={ayuda ? `${base}-ayuda` : undefined}
      />
      <label
        htmlFor={`${base}-control`}
        className={etiquetaOculta ? 'visually-hidden' : estilos.etiqueta}
      >
        {etiqueta}
      </label>
      {ayuda ? (
        <p id={`${base}-ayuda`} className={estilos.ayuda}>
          {ayuda}
        </p>
      ) : null}
    </div>
  );
}
