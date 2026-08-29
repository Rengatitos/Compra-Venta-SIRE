import type { ReactNode } from 'react';

import estilos from './DataTable.module.css';

export interface Columna<T> {
  clave: string;
  cabecera: string;
  /** Alinea a la derecha y usa cifras tabulares. Para montos y conteos. */
  numerica?: boolean;
  monoespaciada?: boolean;
  /** Convierte la celda en `<th scope="row">`: el identificador de la fila. */
  cabeceraDeFila?: boolean;
  /**
   * Ancho mínimo, p. ej. `'16rem'`. La tabla ocupa el 100 %, así que sin esto
   * una columna de texto largo se estrangula hasta partir cada palabra. Con él
   * la tabla desborda y usa el desplazamiento de su región.
   */
  anchoMinimo?: string;
  render: (fila: T) => ReactNode;
}

interface Props<T> {
  /** Se usa como `<caption>` y como nombre accesible de la región desplazable. */
  leyenda: string;
  columnas: readonly Columna<T>[];
  filas: readonly T[];
  claveDeFila: (fila: T) => string;
  /** Contenido a mostrar cuando no hay filas. */
  vacio?: ReactNode;
  /** Oculta el `<caption>` visualmente sin quitarlo del árbol accesible. */
  leyendaOculta?: boolean;
}

/**
 * Tabla de datos real (`<table>`, `<caption>`, `<th scope>`), dentro de una
 * región desplazable enfocable con el teclado: así el desbordamiento horizontal
 * se resuelve donde nace y sigue siendo operable sin ratón.
 */
export function DataTable<T>({
  leyenda,
  columnas,
  filas,
  claveDeFila,
  vacio,
  leyendaOculta = false,
}: Props<T>) {
  if (filas.length === 0 && vacio) return <>{vacio}</>;

  return (
    <div className={estilos.region} role="group" aria-label={leyenda} tabIndex={0}>
      <table className={estilos.tabla}>
        <caption className={leyendaOculta ? 'visually-hidden' : estilos.leyenda}>
          {leyenda}
        </caption>
        <thead>
          <tr>
            {columnas.map((columna) => (
              <th
                key={columna.clave}
                scope="col"
                className={`${estilos.celdaCabecera} ${
                  columna.numerica ? (estilos.numerica ?? '') : ''
                }`}
                style={columna.anchoMinimo ? { minInlineSize: columna.anchoMinimo } : undefined}
              >
                {columna.cabecera}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filas.map((fila) => (
            <tr key={claveDeFila(fila)} className={estilos.fila}>
              {columnas.map((columna) => {
                const clases = [
                  estilos.celda,
                  columna.numerica ? estilos.numerica : '',
                  columna.monoespaciada ? estilos.monoespaciada : '',
                ]
                  .filter(Boolean)
                  .join(' ');

                return columna.cabeceraDeFila ? (
                  <th key={columna.clave} scope="row" className={clases}>
                    {columna.render(fila)}
                  </th>
                ) : (
                  <td key={columna.clave} className={clases}>
                    {columna.render(fila)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface PropsPie {
  /** Texto del recuento, por ejemplo "Mostrando 1–100". */
  recuento: string;
  children?: ReactNode;
}

export function TableFooter({ recuento, children }: PropsPie) {
  return (
    <div className={estilos.pie}>
      <p className={estilos.recuento}>{recuento}</p>
      {children}
    </div>
  );
}
