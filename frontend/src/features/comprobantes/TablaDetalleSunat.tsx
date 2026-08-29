import { useState } from 'react';
import { Link } from 'react-router';

import { Button } from '@/components/ui/Button';
import { DataTable, TableFooter } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { EmptyState } from '@/components/ui/Feedback';
import { formatearCantidad, formatearMoneda } from '@/lib/format';
import layout from '@/styles/layouts.module.css';

import { normalizarDetalleSunat } from './detalleSunat';
import type { ItemDetalle } from './detalleSunat';

interface Props {
  /** `list[Any]` en el backend: la forma la decide el scraping del portal. */
  filas: readonly unknown[];
  moneda: string;
  serieNumero: string;
  periodo: string;
}

export function TablaDetalleSunat({ filas, moneda, serieNumero, periodo }: Props) {
  const [verCrudo, setVerCrudo] = useState(false);
  const { items, descartadas, totalValorVenta, totalIcbper } = normalizarDetalleSunat(filas);

  // El ICBPER solo aplica a las bolsas de plástico: en la mayoría de los
  // comprobantes sería una columna entera de ceros.
  const hayIcbper = items.some((item) => (item.icbper ?? 0) !== 0);

  const columnas: readonly Columna<ItemDetalle>[] = [
    {
      clave: 'descripcion',
      cabecera: 'Descripción',
      cabeceraDeFila: true,
      anchoMinimo: '18rem',
      render: (item) => item.descripcion || '—',
    },
    {
      clave: 'codigo',
      cabecera: 'Código',
      monoespaciada: true,
      render: (item) => item.codigo || '—',
    },
    {
      clave: 'cantidad',
      cabecera: 'Cantidad',
      numerica: true,
      render: (item) => formatearCantidad(item.cantidad),
    },
    {
      clave: 'unidadMedida',
      cabecera: 'U.M.',
      render: (item) => item.unidadMedida || '—',
    },
    {
      clave: 'valorUnitario',
      cabecera: 'Valor unit.',
      numerica: true,
      render: (item) => formatearMoneda(item.valorUnitario, moneda),
    },
    {
      clave: 'precioUnitario',
      cabecera: 'Precio unit.',
      numerica: true,
      render: (item) => formatearMoneda(item.precioUnitario, moneda),
    },
    {
      clave: 'valorVenta',
      cabecera: 'Valor venta',
      numerica: true,
      render: (item) => formatearMoneda(item.valorVenta, moneda),
    },
    ...(hayIcbper
      ? [
          {
            clave: 'icbper',
            cabecera: 'ICBPER',
            numerica: true,
            render: (item: ItemDetalle) => formatearMoneda(item.icbper, moneda),
          },
        ]
      : []),
  ];

  return (
    <>
      {filas.length === 0 ? (
        <EmptyState
          titulo="Sin detalle extraído"
          texto="Lanza la extracción de detalle del periodo para traer los ítems de este comprobante."
          accion={
            <Link to={`/periodos/${encodeURIComponent(periodo)}`}>
              Ir a la extracción de detalle
            </Link>
          }
        />
      ) : (
        <>
          <div className={layout.filaFin}>
            <Button
              pequeno
              variante="fantasma"
              aria-expanded={verCrudo}
              onClick={() => setVerCrudo((previo) => !previo)}
            >
              {verCrudo ? 'Ocultar el JSON original' : 'Ver el JSON original'}
            </Button>
          </div>

          <DataTable
            leyenda={`Ítems que el portal SOL declara para ${serieNumero}`}
            leyendaOculta
            columnas={columnas}
            filas={items}
            claveDeFila={(item) => String(item.indice)}
            vacio={
              <EmptyState
                titulo="El detalle llegó vacío"
                texto="El portal respondió, pero ninguna de sus filas tenía producto ni código. Vuelve a lanzar la extracción del periodo."
              />
            }
          />

          {items.length > 0 ? (
            <TableFooter recuento={`${items.length} ítem(s)`}>
              <p className={layout.textoSecundario}>
                Valor de venta: <strong>{formatearMoneda(totalValorVenta, moneda)}</strong>
                {hayIcbper ? ` · ICBPER: ${formatearMoneda(totalIcbper, moneda)}` : ''}
              </p>
            </TableFooter>
          ) : null}

          {descartadas > 0 ? (
            <p className={layout.textoSecundario}>
              {descartadas} fila(s) del portal no se pudieron interpretar y quedaron fuera de
              la tabla. Están en el JSON original.
            </p>
          ) : null}

          {verCrudo ? (
            <pre className={layout.preformateado}>{JSON.stringify(filas, null, 2)}</pre>
          ) : null}
        </>
      )}
    </>
  );
}
