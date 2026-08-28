import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { exportarLote, listarComprobantes } from '@/api/comprobantes';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable, TableFooter } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { SelectField } from '@/components/ui/Field';
import { Pagination } from '@/components/ui/Pagination';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { NoEncontradaPage } from '@/features/shared/NoEncontradaPage';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearFecha, formatearMoneda, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ComprobanteResponse } from '@/types/api';
import type { FormatoExport } from '@/types/domain';
import { esPeriodoValido } from '@/types/domain';

import { presentarEstadoComprobante, presentarResultadoIA } from './estadoComprobante';

const POR_PAGINA = 100;

export function ComprobantesPage() {
  const { periodo = '' } = useParams();
  const ruc = useRuc();
  const { mostrar } = useToast();

  const [pagina, setPagina] = useState(1);
  const [exportando, setExportando] = useState<FormatoExport | null>(null);

  useDocumentTitle(`Comprobantes ${formatearPeriodo(periodo)}`);

  const comprobantes = useQuery({
    queryKey: ['comprobantes', ruc, periodo, pagina],
    queryFn: () =>
      listarComprobantes(ruc, periodo, {
        libro: 'compras',
        limit: POR_PAGINA,
        skip: (pagina - 1) * POR_PAGINA,
      }),
    enabled: esPeriodoValido(periodo),
  });

  if (!esPeriodoValido(periodo)) return <NoEncontradaPage />;

  async function exportar(formato: FormatoExport) {
    setExportando(formato);
    try {
      await exportarLote(ruc, periodo, formato);
    } catch (fallo) {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo exportar',
        detalle:
          fallo instanceof ApiError && fallo.esNoEncontrado
            ? 'El periodo no tiene comprobantes que exportar.'
            : fallo instanceof ApiError
              ? fallo.message
              : 'Error inesperado.',
      });
    } finally {
      setExportando(null);
    }
  }

  const filas = comprobantes.data ?? [];

  const columnas: readonly Columna<ComprobanteResponse>[] = [
    {
      clave: 'serie_numero',
      cabecera: 'Comprobante',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => (
        <Link
          to={`/periodos/${encodeURIComponent(periodo)}/comprobantes/${encodeURIComponent(
            fila.serie_numero,
          )}`}
        >
          {fila.serie_numero}
        </Link>
      ),
    },
    {
      clave: 'fecha_emision',
      cabecera: 'Emisión',
      monoespaciada: true,
      render: (fila) => formatearFecha(fila.fecha_emision),
    },
    {
      clave: 'razon_social',
      cabecera: 'Contraparte',
      render: (fila) => fila.razon_social || '—',
    },
    {
      clave: 'documento_contraparte',
      cabecera: 'RUC / Doc.',
      monoespaciada: true,
      render: (fila) => fila.documento_contraparte || '—',
    },
    {
      clave: 'igv',
      cabecera: 'IGV',
      numerica: true,
      render: (fila) => formatearMoneda(fila.igv, fila.moneda),
    },
    {
      clave: 'total',
      cabecera: 'Total',
      numerica: true,
      render: (fila) => formatearMoneda(fila.total, fila.moneda),
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (fila) => {
        const estado = presentarEstadoComprobante(fila.estado_procesamiento);
        const resultado = presentarResultadoIA(fila.analisis?.resultado ?? null);
        return (
          <div className={layout.fila}>
            <Badge tono={estado.tono} conPunto>
              {estado.texto}
            </Badge>
            {resultado ? <Badge tono={resultado.tono}>{resultado.texto}</Badge> : null}
          </div>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        titulo={`Comprobantes · ${formatearPeriodo(periodo)}`}
        descripcion="Registro de compras (RCE) sincronizado desde el SIRE. Solo se guardan series que empiezan por F o E."
        acciones={
          <>
            <Button
              onClick={() => void exportar('excel')}
              cargando={exportando === 'excel'}
              disabled={exportando !== null}
            >
              Exportar Excel
            </Button>
            <Button
              onClick={() => void exportar('pdf')}
              cargando={exportando === 'pdf'}
              disabled={exportando !== null}
            >
              Exportar PDF
            </Button>
          </>
        }
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Procesar el periodo"
          descripcion="La extracción de detalle hace scraping del portal SOL y corre en segundo plano; el análisis con IA clasifica los comprobantes pendientes."
        >
          <div className={layout.fila}>
            <Link to={`/periodos/${encodeURIComponent(periodo)}/detalle`}>
              Extraer detalle de ítems
            </Link>
            <span aria-hidden="true">·</span>
            <Link to={`/periodos/${encodeURIComponent(periodo)}/analisis`}>
              Analizar con IA
            </Link>
            <span aria-hidden="true">·</span>
            <Link to="/periodos">Volver a periodos</Link>
          </div>
        </Panel>

        <Panel
          titulo="Listado"
          acciones={
            <SelectField
              etiqueta="Libro"
              value="compras"
              onChange={() => undefined}
              opciones={[
                { valor: 'compras', texto: 'Compras (RCE)' },
                { valor: 'ventas', texto: 'Ventas (RVIE) — no disponible', deshabilitada: true },
              ]}
              ayuda="El registro de ventas todavía no está implementado en la API."
            />
          }
        >
          {comprobantes.isPending ? (
            <Skeleton lineas={6} etiqueta="Cargando comprobantes" />
          ) : null}

          {comprobantes.isError ? (
            <ErrorState
              titulo={
                comprobantes.error instanceof ApiError && comprobantes.error.esNoEncontrado
                  ? 'El periodo no existe para esta empresa'
                  : 'No se pudieron cargar los comprobantes'
              }
              texto={
                comprobantes.error instanceof ApiError
                  ? comprobantes.error.message
                  : 'Error inesperado.'
              }
              accion={
                <Button pequeno onClick={() => void comprobantes.refetch()}>
                  Reintentar
                </Button>
              }
            />
          ) : null}

          {comprobantes.data ? (
            <>
              <DataTable
                leyenda={`Comprobantes de compras del periodo ${formatearPeriodo(periodo)}`}
                leyendaOculta
                columnas={columnas}
                filas={filas}
                claveDeFila={(fila) => fila.serie_numero}
                vacio={
                  <EmptyState
                    titulo="Este periodo no tiene comprobantes"
                    texto="Sincroniza la propuesta del SIRE desde la pantalla de periodos para traerlos."
                    accion={<Link to="/periodos">Ir a periodos</Link>}
                  />
                }
              />
              {filas.length > 0 ? (
                <TableFooter
                  recuento={`Mostrando ${(pagina - 1) * POR_PAGINA + 1}–${
                    (pagina - 1) * POR_PAGINA + filas.length
                  }`}
                >
                  <Pagination
                    pagina={pagina}
                    haySiguiente={filas.length === POR_PAGINA}
                    onCambiar={setPagina}
                  />
                </TableFooter>
              ) : null}
            </>
          ) : null}
        </Panel>
      </div>
    </>
  );
}
