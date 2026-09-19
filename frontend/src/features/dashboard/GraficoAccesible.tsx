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
  /**
   * Si la tabla se ve o solo la leen las tecnologías de asistencia. Existe
   * siempre: es la alternativa textual del gráfico y sin ella el SVG no diría
   * nada a un lector de pantalla. Se muestra cuando los valores exactos aportan
   * —las contrapartes y sus montos se consultan uno a uno— y se deja oculta
   * cuando el gráfico ya cuenta lo que hay que ver, como la forma de una serie
   * diaria.
   */
  tabla?: 'visible' | 'oculta';
  /** El gráfico. Queda fuera del foco y del árbol accesible: la versión
   *  accesible es la tabla. */
  children: ReactNode;
}

/**
 * Un gráfico SVG no es legible por un lector de pantalla, así que cada gráfico
 * va acompañado de la misma serie como tabla real.
 */
export function GraficoAccesible({
  leyenda,
  encabezadoNombre,
  encabezadoValor,
  filas,
  tabla = 'oculta',
  children,
}: Props) {
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

      <div className={tabla === 'visible' ? undefined : 'visually-hidden'}>
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
