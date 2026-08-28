import type { ReactNode } from 'react';

import estilos from './PageHeader.module.css';

interface Props {
  /** Único `<h1>` de la pantalla. */
  titulo: string;
  descripcion?: string;
  acciones?: ReactNode;
}

export function PageHeader({ titulo, descripcion, acciones }: Props) {
  return (
    <div className={estilos.cabecera}>
      <div className={estilos.textos}>
        <h1 className={estilos.titulo}>{titulo}</h1>
        {descripcion ? <p className={estilos.descripcion}>{descripcion}</p> : null}
      </div>
      {acciones ? <div className={estilos.acciones}>{acciones}</div> : null}
    </div>
  );
}
