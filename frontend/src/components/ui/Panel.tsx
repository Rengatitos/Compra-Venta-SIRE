import { useId } from 'react';
import type { ReactNode } from 'react';

import estilos from './Panel.module.css';

interface Props {
  /** Encabezado del panel. Se enlaza al `<section>` con aria-labelledby. */
  titulo: string;
  descripcion?: string;
  acciones?: ReactNode;
  interactivo?: boolean;
  children: ReactNode;
}

/**
 * Contenedor base de todo el dashboard: un `<section>` real con su `<h2>`, para
 * que la página se pueda recorrer por encabezados y por regiones.
 */
export function Panel({
  titulo,
  descripcion,
  acciones,
  interactivo = false,
  children,
}: Props) {
  const idTitulo = useId();

  return (
    <section
      className={`${estilos.panel} ${interactivo ? (estilos.interactivo ?? '') : ''}`}
      aria-labelledby={idTitulo}
    >
      <div className={estilos.cabecera}>
        <div className={estilos.textos}>
          <h2 className={estilos.titulo} id={idTitulo}>
            {titulo}
          </h2>
          {descripcion ? <p className={estilos.descripcion}>{descripcion}</p> : null}
        </div>
        {acciones ? <div className={estilos.acciones}>{acciones}</div> : null}
      </div>
      <div className={estilos.cuerpo}>{children}</div>
    </section>
  );
}
