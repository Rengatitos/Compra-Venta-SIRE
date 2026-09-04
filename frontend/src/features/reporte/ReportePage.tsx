import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useParams } from 'react-router';

import { obtenerReporte } from '@/api/auditoria';
import { exportarLote } from '@/api/comprobantes';
import { descargarZipPdfs } from '@/api/pdfs';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { DataTable, TableFooter } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, MetricTile, Skeleton } from '@/components/ui/Feedback';
import { Panel } from '@/components/ui/Panel';
import { comparable, descuadra, presentarFuente } from '@/features/auditoria/coberturaAuditoria';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearMoneda } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { FilaReporte } from '@/types/api';
import { LIBROS } from '@/types/domain';
import type { Libro } from '@/types/domain';

const ETIQUETA_LIBRO: Record<Libro, string> = { compras: 'Compras', ventas: 'Ventas' };

export function ReportePage() {
  const { periodo = '' } = useParams();
  useDocumentTitle(`Reporte ${periodo}`);

  const ruc = useRuc();
  const { mostrar } = useToast();

  const [libro, setLibro] = useState<Libro>('compras');
  const [soloDescuadres, setSoloDescuadres] = useState(false);

  const reporte = useQuery({
    queryKey: ['reporte', ruc, periodo, libro],
    queryFn: () => obtenerReporte(ruc, periodo, libro),
  });

  function alFallarDescarga(titulo: string) {
    return (fallo: unknown) => {
      const vacio = fallo instanceof ApiError && fallo.esNoEncontrado;
      mostrar({
        tono: vacio ? 'neutro' : 'error',
        titulo: vacio ? 'No hay nada que descargar todavía' : titulo,
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    };
  }

  const zip = useMutation({
    mutationFn: () => descargarZipPdfs(ruc, periodo, libro),
    onError: alFallarDescarga('No se pudo descargar el ZIP'),
  });

  const excel = useMutation({
    mutationFn: () => exportarLote(ruc, periodo, 'excel', libro),
    onError: alFallarDescarga('No se pudo exportar el Excel'),
  });

  const resumen = reporte.data?.resumen;
  const todas = reporte.data?.filas ?? [];
  const filas = soloDescuadres ? todas.filter(descuadra) : todas;

  const columnas: readonly Columna<FilaReporte>[] = [
    {
      clave: 'serie_numero',
      cabecera: 'Comprobante',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => fila.serie_numero,
    },
    {
      clave: 'razon_social',
      cabecera: 'Contraparte',
      anchoMinimo: '16rem',
      render: (fila) => fila.razon_social || '—',
    },
    {
      clave: 'total',
      cabecera: 'Total del registro',
      numerica: true,
      render: (fila) => formatearMoneda(fila.total, fila.moneda),
    },
    {
      clave: 'importe_detalle',
      cabecera: 'Suma del detalle',
      numerica: true,
      // Un guion, no un cero: no se extrajo el detalle, no vale cero.
      render: (fila) =>
        fila.importe_detalle === null
          ? '—'
          : formatearMoneda(fila.importe_detalle, fila.moneda),
    },
    {
      clave: 'diferencia',
      cabecera: 'Diferencia',
      numerica: true,
      render: (fila) => {
        if (fila.diferencia === null) return '—';
        return descuadra(fila) ? (
          <Badge tono="error" conPunto>
            {formatearMoneda(fila.diferencia, fila.moneda)}
          </Badge>
        ) : (
          formatearMoneda(fila.diferencia, fila.moneda)
        );
      },
    },
    {
      clave: 'glosa',
      cabecera: 'Glosa',
      anchoMinimo: '22rem',
      render: (fila) => fila.glosa || '—',
    },
    {
      clave: 'cuenta',
      cabecera: 'Cuentas',
      monoespaciada: true,
      render: (fila) =>
        [fila.cuenta_base, fila.cuenta_total].filter(Boolean).join(' / ') || '—',
    },
    {
      clave: 'fuentes',
      cabecera: 'Fuentes',
      anchoMinimo: '14rem',
      render: (fila) => (
        <span className={layout.fila}>
          {fila.fuentes.length === 0 ? '—' : null}
          {fila.fuentes.map((fuente) => {
            const presentacion = presentarFuente(fuente);
            return (
              <Badge key={fuente} tono={presentacion.tono}>
                {presentacion.texto}
              </Badge>
            );
          })}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        titulo={`Reporte de auditoría ${periodo}`}
        descripcion="Enfrenta lo que declara el registro con lo que se leyó del comprobante, y dice de dónde salió cada dato. Las filas sin detalle extraído no cuadran ni descuadran: les falta el dato."
        acciones={
          <ButtonLink variante="fantasma" a={`/periodos/${encodeURIComponent(periodo)}/auditoria`}>
            Recolectar respaldos
          </ButtonLink>
        }
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Resumen"
          acciones={
            <div className={layout.fila}>
              {LIBROS.map((opcion) => (
                <Button
                  key={opcion}
                  pequeno
                  variante={opcion === libro ? 'primario' : 'fantasma'}
                  onClick={() => setLibro(opcion)}
                >
                  {ETIQUETA_LIBRO[opcion]}
                </Button>
              ))}
            </div>
          }
        >
          <div className={layout.pila}>
            {reporte.isPending ? <Skeleton lineas={3} etiqueta="Cargando resumen" /> : null}

            {resumen ? (
              <div className={layout.rejillaMetricas}>
                <MetricTile
                  etiqueta="Comprobantes"
                  valor={String(resumen.comprobantes)}
                  nota={formatearMoneda(resumen.total_registro, 'PEN')}
                />
                <MetricTile
                  etiqueta="Con glosa"
                  valor={`${resumen.con_glosa} / ${resumen.comprobantes}`}
                />
                <MetricTile
                  etiqueta="Con PDF"
                  valor={`${resumen.con_pdf} / ${resumen.comprobantes}`}
                />
                <MetricTile
                  etiqueta="Descuadrados"
                  valor={`${resumen.descuadrados} / ${resumen.comparables}`}
                  nota={
                    resumen.comparables === 0
                      ? 'Nada comparado todavía: falta extraer el detalle'
                      : 'Sobre los que se pudieron comparar'
                  }
                />
              </div>
            ) : null}

            <div className={layout.fila}>
              <Button
                onClick={() => zip.mutate()}
                cargando={zip.isPending}
                disabled={!reporte.data?.zip_disponible}
              >
                Descargar ZIP de PDFs
              </Button>
              <Button
                variante="fantasma"
                onClick={() => excel.mutate()}
                cargando={excel.isPending}
                disabled={todas.length === 0}
              >
                Exportar registro en Excel
              </Button>
              {todas.some(descuadra) ? (
                <Button
                  pequeno
                  variante={soloDescuadres ? 'primario' : 'fantasma'}
                  onClick={() => setSoloDescuadres((previo) => !previo)}
                >
                  {soloDescuadres ? 'Ver todos' : 'Ver solo descuadres'}
                </Button>
              ) : null}
            </div>
          </div>
        </Panel>

        <Panel
          titulo="Tabla comparativa"
          descripcion="Cada fila cita sus fuentes: la propuesta del SIRE, el detalle del portal SOL y el PDF descargado, de menos a más cerca del documento original."
        >
          {reporte.isPending ? <Skeleton lineas={6} etiqueta="Cargando reporte" /> : null}

          {reporte.isError ? (
            <ErrorState
              titulo="No se pudo cargar el reporte"
              texto={
                reporte.error instanceof ApiError
                  ? reporte.error.message
                  : 'Error inesperado.'
              }
              accion={
                <Button pequeno onClick={() => void reporte.refetch()}>
                  Reintentar
                </Button>
              }
            />
          ) : null}

          {reporte.data ? (
            <>
              <DataTable
                leyenda={`Comparativa de ${ETIQUETA_LIBRO[libro]} en ${periodo}`}
                leyendaOculta
                columnas={columnas}
                filas={filas}
                claveDeFila={(fila) => fila.serie_numero}
                vacio={
                  soloDescuadres ? (
                    <EmptyState
                      titulo="Ningún descuadre"
                      texto="Todo lo que se pudo comparar cuadra dentro de un céntimo."
                    />
                  ) : (
                    <EmptyState
                      titulo={`Sin comprobantes de ${ETIQUETA_LIBRO[libro].toLowerCase()}`}
                      texto="Sincroniza la propuesta del SIRE en este periodo para tener algo que auditar."
                    />
                  )
                }
              />
              {filas.length > 0 ? (
                <TableFooter
                  recuento={
                    soloDescuadres
                      ? `${filas.length} descuadres de ${todas.filter(comparable).length} comparables`
                      : `${filas.length} comprobantes`
                  }
                />
              ) : null}
            </>
          ) : null}
        </Panel>
      </div>
    </>
  );
}
