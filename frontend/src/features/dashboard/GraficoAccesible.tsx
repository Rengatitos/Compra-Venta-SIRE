import { useId, useState } from 'react';
import type { ReactNode } from 'react';

import estilos from './Dashboard.module.css';

export interface FilaSerie {
  nombre: string;
  valor: string;
}

interface Props {
  /** Descripción de la serie; se usa como `<caption>` de la tabla equivalente. */
  leyenda: string;
  encabezadoNombre: string;
  encabezadoValor: string;
  filas: readonly FilaSerie[];
  /** El gráfico. Queda fuera del foco y del árbol accesible: la versión
   *  accesible es la tabla. */
  children: ReactNode;
}

/**
 * Un gráfico SVG no es legible por un lector de pantalla, así que cada gráfico
 * va acompañado de la misma serie como tabla real. La tabla existe siempre en el
 * árbol accesible y el botón solo decide si además se ve.
 */
export function GraficoAccesible({
  leyenda,
  encabezadoNombre,
  encabezadoValor,
  filas,
  children,
}: Props) {
  const [visible, setVisible] = useState(false);
  const idTabla = useId();

  return (
    <>
      {/*
        `inert` además de `aria-hidden`: la librería de gráficos añade nodos
        enfocables dentro del SVG, y un elemento enfocable dentro de un
        contenedor aria-hidden es una violación de WCAG (regla aria-hidden-focus
        de axe). `inert` los saca del orden de tabulación y del árbol accesible
        de una vez.
      */}
      <div aria-hidden="true" inert>
        {children}
      </div>

      <button
        type="button"
        className={estilos.alternar}
        onClick={() => setVisible((previo) => !previo)}
        aria-expanded={visible}
        aria-controls={idTabla}
      >
        {visible ? 'Ocultar los datos' : 'Ver los datos'}
      </button>

      <div id={idTabla} className={visible ? undefined : 'visually-hidden'}>
        <table className={estilos.tabla}>
          <caption className={estilos.leyenda}>{leyenda}</caption>
          <thead>
            <tr>
              <th scope="col" className={estilos.celdaCabecera}>
                {encabezadoNombre}
              </th>
              <th scope="col" className={estilos.celdaCabecera}>
                {encabezadoValor}
              </th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila) => (
              <tr key={fila.nombre}>
                <th scope="row" className={estilos.celda}>
                  {fila.nombre}
                </th>
                <td className={estilos.celdaNumerica}>{fila.valor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
