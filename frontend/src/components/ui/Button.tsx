import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react';
import { Link } from 'react-router';

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

interface Apariencia {
  variante: Variante;
  pequeno: boolean;
  pastilla: boolean;
  bloque: boolean;
}

function componerClases({ variante, pequeno, pastilla, bloque }: Apariencia): string {
  return [
    estilos.boton,
    CLASE_VARIANTE[variante],
    pequeno ? estilos.pequeno : '',
    pastilla ? estilos.pastilla : '',
    bloque ? estilos.bloque : '',
  ]
    .filter(Boolean)
    .join(' ');
}

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
  const clases = componerClases({ variante, pequeno, pastilla, bloque });

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

interface PropsEnlace
  extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'className' | 'href'> {
  /** Destino de `react-router`. Se llama `a` para no chocar con el `href` nativo. */
  a: string;
  variante?: Variante;
  pequeno?: boolean;
  pastilla?: boolean;
  bloque?: boolean;
  children: ReactNode;
}

/**
 * Navegación con la apariencia de un botón. Es un `<a>` de verdad, así que
 * conserva el clic con rueda, el menú contextual y el rol de enlace: un
 * `<button>` con `useNavigate` pierde las tres cosas.
 */
export function ButtonLink({
  a,
  variante = 'secundario',
  pequeno = false,
  pastilla = false,
  bloque = false,
  children,
  ...resto
}: PropsEnlace) {
  return (
    <Link {...resto} to={a} className={componerClases({ variante, pequeno, pastilla, bloque })}>
      {children}
    </Link>
  );
}
