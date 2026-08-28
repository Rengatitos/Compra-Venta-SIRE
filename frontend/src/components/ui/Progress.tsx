import estilos from './Progress.module.css';

interface Props {
  etiqueta: string;
  actual: number;
  total: number;
  porcentaje: number;
  mensaje?: string;
}

/**
 * `<progress>` nativo. El mensaje va en una región `aria-live="polite"`, así que
 * el avance se anuncia sin interrumpir lo que el usuario esté leyendo.
 */
export function ProgressBar({ etiqueta, actual, total, porcentaje, mensaje }: Props) {
  const indeterminado = total <= 0;

  return (
    <div className={estilos.contenedor}>
      <div className={estilos.cabecera}>
        <p className={estilos.mensaje} aria-live="polite">
          {mensaje ?? etiqueta}
        </p>
        <p className={estilos.cifra}>
          {indeterminado ? 'En cola' : `${actual} / ${total} · ${Math.round(porcentaje)} %`}
        </p>
      </div>
      <progress
        className={estilos.barra}
        aria-label={etiqueta}
        value={indeterminado ? undefined : actual}
        max={indeterminado ? undefined : total}
      />
    </div>
  );
}
