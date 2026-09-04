import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router';

import { listarComprobantes } from '@/api/comprobantes';
import { iniciarExtraccionDetalle } from '@/api/detalle';
import { descargarZipPdfs, iniciarDescargaPdfs } from '@/api/pdfs';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { DataTable, TableFooter } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, MetricTile, Skeleton } from '@/components/ui/Feedback';
import { Panel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/Progress';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useJobPolling } from '@/hooks/useJobPolling';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ComprobanteResponse } from '@/types/api';
import { LIBROS } from '@/types/domain';
import type { Libro } from '@/types/domain';

import { tieneDetalle, tieneGlosa, tienePdf } from './coberturaAuditoria';

const MAX_FILAS = 500;

const ETIQUETA_LIBRO: Record<Libro, string> = { compras: 'Compras', ventas: 'Ventas' };

export function AuditoriaPage() {
  const { periodo = '' } = useParams();
  useDocumentTitle(`Auditoría ${periodo}`);

  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [libro, setLibro] = useState<Libro>('compras');
  const [jobId, setJobId] = useState<string | null>(null);

  const job = useJobPolling(jobId);

  const comprobantes = useQuery({
    queryKey: ['comprobantes', ruc, periodo, libro, 'auditoria'],
    queryFn: () => listarComprobantes(ruc, periodo, { libro, limit: MAX_FILAS }),
  });

  // Cuando el trabajo termina, lo que hay en pantalla ya no refleja el
  // servidor: se recarga en vez de dejar al usuario recargando a mano. Va en
  // un efecto porque avisar y refrescar son efectos: hacerlo durante el
  // render dispara un bucle de re-render en cuanto llega el estado terminal.
  const estadoJob = job.data?.estado;
  const errorJob = job.data?.error;
  useEffect(() => {
    if (estadoJob !== 'completado' && estadoJob !== 'fallido') return;

    setJobId(null);
    if (estadoJob === 'fallido') {
      mostrar({
        tono: 'error',
        titulo: 'El trabajo falló',
        detalle: errorJob ?? 'Revisa los procesos para ver el detalle.',
      });
    } else {
      mostrar({ tono: 'exito', titulo: 'Trabajo terminado' });
    }
    void cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
  }, [estadoJob, errorJob, mostrar, cliente, ruc, periodo]);

  function alFallar(titulo: string) {
    return (fallo: unknown) => {
      // Un 409 no es un error del usuario: significa que ya hay algo en marcha.
      const conflicto = fallo instanceof ApiError && fallo.esConflicto;
      mostrar({
        tono: conflicto ? 'neutro' : 'error',
        titulo: conflicto ? 'Ya hay un trabajo en curso' : titulo,
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    };
  }

  const extraer = useMutation({
    mutationFn: () => iniciarExtraccionDetalle(ruc, periodo, libro),
    onSuccess: (respuesta) => {
      setJobId(respuesta.job_id);
      mostrar({ tono: 'exito', titulo: 'Extracción iniciada', detalle: respuesta.mensaje });
    },
    onError: alFallar('No se pudo iniciar la extracción'),
  });

  const descargar = useMutation({
    mutationFn: () => iniciarDescargaPdfs(ruc, periodo, libro),
    onSuccess: (respuesta) => {
      setJobId(respuesta.job_id);
      mostrar({ tono: 'exito', titulo: 'Descarga iniciada', detalle: respuesta.mensaje });
    },
    onError: alFallar('No se pudo iniciar la descarga de PDFs'),
  });

  const zip = useMutation({
    mutationFn: () => descargarZipPdfs(ruc, periodo, libro),
    onError: (fallo) => {
      const vacio = fallo instanceof ApiError && fallo.esNoEncontrado;
      mostrar({
        tono: vacio ? 'neutro' : 'error',
        titulo: vacio ? 'Todavía no hay PDFs' : 'No se pudo descargar el ZIP',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const filas = comprobantes.data ?? [];
  const conDetalle = filas.filter((fila) => fila.detalle_sunat.length > 0).length;
  const conPdf = filas.filter((fila) => fila.pdf_sunat?.ruta).length;
  const hayTrabajo = jobId !== null || extraer.isPending || descargar.isPending;

  const columnas: readonly Columna<ComprobanteResponse>[] = [
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
      anchoMinimo: '18rem',
      render: (fila) => fila.razon_social || '—',
    },
    {
      clave: 'detalle',
      cabecera: 'Detalle de ítems',
      render: (fila) => {
        const estado = tieneDetalle(fila);
        return (
          <Badge tono={estado.tono} conPunto>
            {estado.texto}
          </Badge>
        );
      },
    },
    {
      clave: 'pdf',
      cabecera: 'PDF',
      render: (fila) => {
        const estado = tienePdf(fila);
        return (
          <Badge tono={estado.tono} conPunto>
            {estado.texto}
          </Badge>
        );
      },
    },
    {
      clave: 'glosa',
      cabecera: 'Glosa',
      render: (fila) => {
        const estado = tieneGlosa(fila);
        return (
          <Badge tono={estado.tono} conPunto>
            {estado.texto}
          </Badge>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        titulo={`Auditoría del periodo ${periodo}`}
        descripcion="Reúne el respaldo de cada comprobante: el detalle de ítems del portal SOL, el PDF del documento y la glosa que produce la clasificación contable."
        acciones={
          <ButtonLink variante="fantasma" a={`/periodos/${encodeURIComponent(periodo)}/reporte`}>
            Ver reporte
          </ButtonLink>
        }
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Recolección"
          descripcion="Los dos trabajos entran al portal SOL con la sesión SOL de la empresa, que es única: si lanzas uno mientras otro corre, el segundo espera su turno."
          acciones={
            <div className={layout.fila}>
              {LIBROS.map((opcion) => (
                <Button
                  key={opcion}
                  pequeno
                  variante={opcion === libro ? 'primario' : 'fantasma'}
                  onClick={() => setLibro(opcion)}
                  disabled={hayTrabajo}
                >
                  {ETIQUETA_LIBRO[opcion]}
                </Button>
              ))}
            </div>
          }
        >
          <div className={layout.pila}>
            <div className={layout.rejillaMetricas}>
              <MetricTile
                etiqueta="Comprobantes"
                valor={String(filas.length)}
                nota={filas.length === MAX_FILAS ? `Se muestran los primeros ${MAX_FILAS}` : undefined}
              />
              <MetricTile
                etiqueta="Con detalle de ítems"
                valor={`${conDetalle} / ${filas.length}`}
              />
              <MetricTile etiqueta="Con PDF guardado" valor={`${conPdf} / ${filas.length}`} />
            </div>

            <div className={layout.fila}>
              <Button
                onClick={() => extraer.mutate()}
                cargando={extraer.isPending}
                disabled={hayTrabajo || filas.length === 0}
              >
                Extraer detalle
              </Button>
              <Button
                onClick={() => descargar.mutate()}
                cargando={descargar.isPending}
                disabled={hayTrabajo || filas.length === 0}
              >
                Descargar PDFs
              </Button>
              <Button
                variante="fantasma"
                onClick={() => zip.mutate()}
                cargando={zip.isPending}
                disabled={conPdf === 0}
              >
                Descargar ZIP
              </Button>
            </div>

            {job.data ? (
              <ProgressBar
                etiqueta="Avance del trabajo"
                actual={job.data.progreso.actual}
                total={job.data.progreso.total}
                porcentaje={job.data.progreso.porcentaje}
                mensaje={job.data.progreso.mensaje}
              />
            ) : null}
          </div>
        </Panel>

        <Panel
          titulo="Cobertura por comprobante"
          descripcion="Las tres columnas se consiguen por caminos distintos, así que se muestran por separado: lo que importa es cuál falta."
        >
          {comprobantes.isPending ? (
            <Skeleton lineas={5} etiqueta="Cargando comprobantes" />
          ) : null}

          {comprobantes.isError ? (
            <ErrorState
              titulo="No se pudieron cargar los comprobantes"
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
                leyenda={`Cobertura de auditoría de ${ETIQUETA_LIBRO[libro]} en ${periodo}`}
                leyendaOculta
                columnas={columnas}
                filas={filas}
                claveDeFila={(fila) => `${fila.libro}-${fila.serie_numero}`}
                vacio={
                  <EmptyState
                    titulo={`Sin comprobantes de ${ETIQUETA_LIBRO[libro].toLowerCase()}`}
                    texto="Sincroniza la propuesta del SIRE en este periodo antes de recolectar respaldos."
                  />
                }
              />
              {filas.length > 0 ? (
                <TableFooter recuento={`${filas.length} comprobantes`} />
              ) : null}
            </>
          ) : null}
        </Panel>
      </div>
    </>
  );
}
