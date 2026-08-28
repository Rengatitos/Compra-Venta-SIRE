import type { ButtonHTMLAttributes, ReactNode } from 'react';

import estilos from './Button.module.css';

type Variante = 'primario' | 'secundario' | 'fantasma' | 'peligro';

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'> {
  variante?: Variante;
  pequeno?: boolean;
  pastilla?: boolean;
  bloque?: boolean;
  /** Muestra el girador, marca `aria-busy` y bloquea el botón. */
  cargando?: boolean;
  children: ReactNode;
}

const CLASE_VARIANTE: Record<Variante, string> = {
  primario: estilos.primario ?? '',
  secundario: '',
  fantasma: estilos.fantasma ?? '',
  peligro: estilos.peligro ?? '',
};

export function Button({
  variante = 'secundario',
  pequeno = false,
  pastilla = false,
  bloque = false,
  cargando = false,
  disabled = false,
  type = 'button',
  children,
  ...resto
}: Props) {
  const clases = [
    estilos.boton,
    CLASE_VARIANTE[variante],
    pequeno ? estilos.pequeno : '',
    pastilla ? estilos.pastilla : '',
    bloque ? estilos.bloque : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      {...resto}
      type={type}
      className={clases}
      disabled={disabled || cargando}
      aria-busy={cargando || undefined}
    >
      {cargando ? <span className={estilos.girador} aria-hidden="true" /> : null}
      {children}
    </button>
  );
}
