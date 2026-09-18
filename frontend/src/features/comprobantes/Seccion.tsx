import { useId } from 'react';
import type { ReactNode } from 'react';

import layout from '@/styles/layouts.module.css';

import estilos from './Seccion.module.css';

/**
 * Bloque de una ficha dentro de un modal. A diferencia de `Panel`, no lleva
 * tarjeta: la tarjeta ya es el propio diálogo y anidar dos superficies iguales
 * solo añade ruido. Lo usan tanto la ficha del comprobante como la del NPD.
 */
export function Seccion({
  titulo,
  acciones,
  children,
}: {
  titulo: string;
  acciones?: ReactNode;
  children: ReactNode;
}) {
  const idTitulo = useId();

  return (
    <section className={estilos.seccion} aria-labelledby={idTitulo}>
      <div className={estilos.cabecera}>
        <h3 className={estilos.titulo} id={idTitulo}>
          {titulo}
        </h3>
        {acciones}
      </div>
      {children}
    </section>
  );
}

/** Par término/valor de las listas de definiciones de una ficha. */
export function Dato({
  termino,
  children,
  className,
}: {
  termino: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className={layout.termino}>{termino}</dt>
      <dd className={layout.descripcion}>{children}</dd>
    </div>
  );
}
