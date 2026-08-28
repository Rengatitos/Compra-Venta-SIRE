import type { ReactNode } from 'react';

import estilos from './Badge.module.css';

export type TonoInsignia = 'neutro' | 'exito' | 'aviso' | 'error' | 'info';

interface Props {
  tono?: TonoInsignia;
  /** Punto de color como refuerzo visual; el significado siempre va en el texto. */
  conPunto?: boolean;
  children: ReactNode;
}

export function Badge({ tono = 'neutro', conPunto = false, children }: Props) {
  return (
    <span className={`${estilos.insignia} ${estilos[tono] ?? ''}`}>
      {conPunto ? <span className={estilos.punto} aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
