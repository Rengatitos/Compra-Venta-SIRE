import { formatearImporteComprobante } from '@/lib/importesComprobante';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { listarIncompletos } from '@/api/comprobantes';
import { descargarReporteAsociado, obtenerEstadoReporteAsociado } from '@/api/auditoria';
import { Link, useParams, useSearchParams } from 'react-router';
import { obtenerJob } from '@/api/jobs';
import {
  exportarLote,
  listarComprobantes,
  listarAnuladosSunat,
  obtenerCoberturaSunat,
} from '@/api/comprobantes';
import { iniciarExtraccionDetalle } from '@/api/detalle';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { DataTable, TableFooter } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, MetricTile, Skeleton } from '@/components/ui/Feedback';
import { Pagination } from '@/components/ui/Pagination';
import { Panel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/Progress';
import { useRuc } from '@/features/auth/useAuth';
import { presentarEstadoJob, presentarTipoJob } from '@/features/jobs/estadoJob';
import { useJobs } from '@/features/jobs/useJobs';
import { NoEncontradaPage } from '@/features/shared/NoEncontradaPage';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearEntero, formatearFecha, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ComprobanteResponse, JobResponse, ResultadoExtraccion } from '@/types/api';
import type { FormatoExport, Libro } from '@/types/domain';
import { ESTADOS_JOB_TERMINALES, esPeriodoValido } from '@/types/domain';

import estilos from './ComprobantesPage.module.css';
import { DialogComprobante } from './DialogComprobante';
import { DescargarDetraccionesButton, DetraccionCelda, NpdPanel } from './Detracciones';
import { DescargarPdfsButton } from './DescargarPdfsButton';
import { presentarEstadoComprobante } from './estadoComprobante';

const POR_PAGINA = 100;

const LIBROS: readonly Libro[] = ['compras', 'ventas'];
const ETIQUETA_LIBRO: Record<Libro, string> = {
  compras: 'Compras (RCE)',
  ventas: 'Ventas (RVIE)',
};
const NOMBRE_REGISTRO: Record<Libro, string> = {
  compras: 'Registro de compras',
  ventas: 'Registro de ventas',
};

/** Exportaciones del libro que está a la vista. */
type Descarga = 'excel' | 'pdf';

/** Qué respaldo del portal SOL tiene ya el comprobante. */
function RespaldoCelda({ fila }: { fila: ComprobanteResponse }) {
  const conDetalle = fila.detalle_sunat.length > 0;
  const conPdf = Boolean(fila.pdf_sunat?.ruta);
  if (!conDetalle && !conPdf) return <>—</>;
  return (
    <div className={estilos.respaldo}>
      {conDetalle ? <Badge tono="info">Detalle</Badge> : null}
      {conPdf ? <Badge tono="info">PDF</Badge> : null}
    </div>
  );
}

export function ComprobantesPage() {
  const { periodo = '' } = useParams();
  const [parametros, setParametros] = useSearchParams();
  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const { seguidos, porId, seguir } = useJobs();

  // La ficha es un modal sobre el listado, pero su identidad vive en la URL:
  // así el enlace se comparte, «atrás» cierra el modal y el clic con rueda
  // sigue funcionando sobre el número de comprobante.
  const abierto = parametros.get('comprobante');

  const [libro, setLibro] = useState<Libro>('compras');
  const [pagina, setPagina] = useState(1);
  const [verAnulados, setVerAnulados] = useState(false);
  const [verIncompletos, setVerIncompletos] = useState(false);
  const listadoRef = useRef<HTMLDivElement>(null);

  function irAAnulados() {
    setVerIncompletos(false);
    setVerAnulados(true);
    window.requestAnimationFrame(() => {
      listadoRef.current?.focus({ preventScroll: true });
      listadoRef.current?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'instant'
          : 'smooth',
        block: 'start',
      });
    });
  }
  const [exportando, setExportando] = useState<Descarga | null>(null);
  const [dialogoExtraccion, setDialogoExtraccion] = useState(false);
  const [extraccion, setExtraccion] = useState<ResultadoExtraccion | null>(null);

  useDocumentTitle(`Comprobantes ${formatearPeriodo(periodo)}`);

  const comprobantes = useQuery({
    queryKey: ['comprobantes', ruc, periodo, libro, pagina],
    queryFn: () =>
      listarComprobantes(ruc, periodo, {
        libro,
        limit: POR_PAGINA,
        skip: (pagina - 1) * POR_PAGINA,
      }),
    enabled: esPeriodoValido(periodo),
  });

  // El seguimiento vive en `JobsProvider`, así que el avance sigue visible
  // aunque se navegue fuera y se vuelva, y también tras recargar.
  // Los trabajos vivos de este periodo, por libro. Sin filtrar por libro, una
  // extracción de compras pintaba su avance bajo la vista de ventas: se veía
  // «Extrayendo E001-789 (6 de 87)» en un libro que sólo tiene 4 comprobantes.
  const jobsVivos = seguidos
    .map((jobId) => porId[jobId])
    .filter(
      (job): job is JobResponse =>
        job !== undefined &&
        job.periodo === periodo &&
        !ESTADOS_JOB_TERMINALES.includes(job.estado),
    );

  const jobActivo = jobsVivos.find((job) => job.libro === libro);
  // El de otro libro no bloquea el botón —el backend lo encola— pero conviene
  // decir que está ahí: explica por qué esta extracción puede tardar en
  // arrancar.
  const otroLibro = jobsVivos.find((job) => job.libro !== libro);

  const cobertura = useQuery({
    queryKey: ['comprobantes', ruc, periodo, libro, 'cobertura-sunat'],
    queryFn: () => obtenerCoberturaSunat(ruc, periodo, libro),
    enabled: esPeriodoValido(periodo),
    refetchInterval: jobActivo ? 5000 : false,
  });

  const reporteAsociado = useQuery({
    queryKey: ['reporte-asociado', ruc, periodo],
    queryFn: () => obtenerEstadoReporteAsociado(ruc, periodo),
    enabled: esPeriodoValido(periodo),
  });

  const descargarAsociado = useMutation({
    mutationFn: () => descargarReporteAsociado(ruc, periodo),
    onError: (fallo) => mostrar({
      tono: 'error',
      titulo: 'No se pudo descargar el reporte asociado',
      detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
    }),
  });

  const anulados = useQuery({
    queryKey: ['comprobantes', ruc, periodo, libro, 'anulados-sunat'],
    queryFn: () => listarAnuladosSunat(ruc, periodo, libro),
    enabled: esPeriodoValido(periodo),
    refetchInterval: jobActivo ? 5000 : false,
  });

  const incompletos = useQuery({
    queryKey: ['comprobantes', ruc, periodo, libro, 'incompletos'],
    queryFn: () => listarIncompletos(ruc, periodo, libro),
    enabled: esPeriodoValido(periodo),
    refetchInterval: jobActivo ? 5000 : false,
  });

  const extraer = useMutation({
    mutationFn: async () => {
      const aceptado = await iniciarExtraccionDetalle(ruc, periodo, libro);
      seguir(aceptado.job_id);
      for (;;) {
        const job = await obtenerJob(aceptado.job_id);
        if (job.estado === 'fallido') {
          throw new Error(job.error || 'No se pudo completar los datos con SUNAT.');
        }
        if (job.estado === 'completado') {
          setExtraccion((job.resultado as ResultadoExtraccion | null) ?? null);
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
      }
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
      await cliente.invalidateQueries({ queryKey: ['reporte-asociado', ruc, periodo] });
    },
    onSuccess: async () => {
      setDialogoExtraccion(false);
      mostrar({ tono: 'exito', titulo: 'Extracción de glosa completada' });
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'El proceso no se completó',
        detalle:
          fallo instanceof ApiError && fallo.esLimiteDeTasa
            ? 'Se alcanzó el límite de solicitudes. Espera un momento.'
            : fallo instanceof Error
              ? fallo.message
              : 'Error inesperado.',
      });
    },
  });

  if (!esPeriodoValido(periodo)) return <NoEncontradaPage />;

  async function exportar(descarga: Descarga, formato: FormatoExport) {
    setExportando(descarga);
    try {
      await exportarLote(ruc, periodo, formato, libro);
    } catch (fallo) {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo exportar',
        detalle:
          fallo instanceof ApiError && fallo.esNoEncontrado
            ? `El periodo no tiene comprobantes de ${libro} que exportar.`
            : fallo instanceof Error
              ? fallo.message
              : 'Error inesperado.',
      });
    } finally {
      setExportando(null);
    }
  }

  function cambiarLibro(nuevo: Libro) {
    if (nuevo === libro) return;
    setLibro(nuevo);
    setPagina(1);
    setExtraccion(null);
  }

  const filas =
    (verIncompletos ? incompletos.data : verAnulados ? anulados.data : comprobantes.data) ?? [];

  const columnas: readonly Columna<ComprobanteResponse>[] = [
    {
      clave: 'serie_numero',
      cabecera: 'Comprobante',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => (
        <Link to={`?comprobante=${encodeURIComponent(fila.serie_numero)}`}>
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
      clave: 'glosa',
      cabecera: verAnulados ? 'Descripción SUNAT' : 'Glosa',
      anchoMinimo: '16rem',
      render: (fila) =>
        verAnulados ? (
          <mark>
            {fila.detalle_sunat
              .map((item) =>
                item &&
                typeof item === 'object' &&
                'descripcion' in item &&
                typeof item.descripcion === 'string'
                  ? item.descripcion
                  : '',
              )
              .filter((descripcion) => /\banulad[oa]s?\b/i.test(descripcion ?? ''))
              .join(' / ')}
          </mark>
        ) : (
          (fila.glosa ?? '—')
        ),
    },
    {
      clave: 'observacion',
      cabecera: 'Observación',
      render: (fila) => fila.observacion || '—',
    },
    {
      clave: 'igv',
      cabecera: 'IGV',
      numerica: true,
      render: (fila) => formatearImporteComprobante(fila.igv, fila),
    },
    {
      clave: 'total',
      cabecera: 'Total',
      numerica: true,
      render: (fila) => formatearImporteComprobante(fila.total, fila),
    },
    ...(libro === 'compras'
      ? [
          {
            clave: 'detraccion',
            cabecera: 'Detracción',
            render: (fila: ComprobanteResponse) => <DetraccionCelda fila={fila} />,
          },
        ]
      : []),
    {
      clave: 'respaldo',
      cabecera: 'Respaldo SOL',
      render: (fila) => <RespaldoCelda fila={fila} />,
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (fila) => {
        const estado = presentarEstadoComprobante(fila.estado_procesamiento);
        return (
          <div className={layout.fila}>
            <Badge tono={estado.tono} conPunto>
              {estado.texto}
            </Badge>
          </div>
        );
      },
    },
  ];
 
  return (
    <> 
      <PageHeader
        titulo={`Comprobantes · ${formatearPeriodo(periodo)}`}
        descripcion={
          libro === 'compras'
            ? 'Registro de compras (RCE) sincronizado desde el SIRE. Solo se guardan series que empiezan por F o E.'
            : 'Registro de ventas (RVIE) sincronizado desde el SIRE. Solo se guardan series que empiezan por F, B o E.'
        }
        acciones={
          <>
            <ButtonLink a="/periodos" variante="fantasma">
              Volver a periodos
            </ButtonLink>
            <div className={estilos.libros} role="group" aria-label="Libro">
              {LIBROS.map((opcion) => (
                <Button
                  key={opcion}
                  pequeno
                  pastilla
                  variante={opcion === libro ? 'primario' : 'fantasma'}
                  aria-pressed={opcion === libro}
                  disabled={extraer.isPending}
                  onClick={() => cambiarLibro(opcion)}
                >
                  {ETIQUETA_LIBRO[opcion]}
                </Button>
              ))}
            </div>
            <Button
              onClick={() => void exportar('excel', 'excel')}
              cargando={exportando === 'excel'}
              disabled={exportando !== null}
              title={`Excel con la plantilla Contasis del ${NOMBRE_REGISTRO[libro].toLowerCase()}`}
            >
              Excel · {NOMBRE_REGISTRO[libro]}
            </Button>
            <Button
              onClick={() => void exportar('pdf', 'pdf')}
              cargando={exportando === 'pdf'}
              disabled={exportando !== null}
              title={`PDF del listado de ${libro} con los datos de SUNAT`}
            >
              PDF del listado
            </Button>
            <DescargarPdfsButton ruc={ruc} periodo={periodo} libro={libro} />
            <Button
              variante="azul"
              onClick={() => descargarAsociado.mutate()}
              cargando={descargarAsociado.isPending}
              disabled={!reporteAsociado.data?.habilitado || descargarAsociado.isPending}
              title={
                reporteAsociado.data?.habilitado
                  ? 'Descarga el Excel y los comprobantes de compras y ventas'
                  : 'Completa las glosas de compras y ventas para habilitar la descarga'
              }
            >
              Descargar reporte y asociado
            </Button>
          </>
        }
      />

      <div className={layout.pilaAmplia}>
        {(incompletos.data?.length ?? 0) > 0 ? (
          <button
            type="button"
            className={estilos.avisoIncompletos}
            onClick={() => {
              irAAnulados();
              setVerAnulados(false);
              setVerIncompletos(true);
            }}
          >
            <strong>⚠ {incompletos.data?.length} comprobantes incompletos · Revisar →</strong>
            <span>
              Algunos comprobantes se encuentran pendientes de completar porque el proceso
              automatizado no pudo recuperar ciertos campos relevantes. Revíselos en la sección
              Incompletos. Si considera que completar estos campos no es relevante, omita este
              mensaje. Se incluirán de todas formas en el reporte.
            </span>
          </button>
        ) : null}
        {(anulados.data?.length ?? 0) > 0 ? (
          <div role="alert">
            <Button variante="peligro" pastilla onClick={irAAnulados}>
              <span aria-hidden="true">⚠</span>
              {anulados.data?.length === 1
                ? '1 comprobante reportado con descripción «Anulado»'
                : `${anulados.data?.length} comprobantes reportados con descripción «Anulado»`}
              <span>Revisar anulados →</span>
            </Button>
          </div>
        ) : null}
        <Panel
          titulo="Procesar el periodo"
          descripcion={`Consulta el portal SOL para obtener el detalle, la glosa y el PDF de los comprobantes pendientes.${libro === 'ventas' ? ' También completa Contraparte y RUC / Doc. faltantes en SIRE cuando aparecen en el comprobante, aunque ya tenga glosa y PDF.' : ''} La tabla se actualiza al terminar.`}
        >
          <div className={layout.rejillaMetricas}>
            <MetricTile
              etiqueta="Con detalle SOL"
              valor={
                cobertura.data ? `${cobertura.data.con_detalle} / ${cobertura.data.total}` : '—'
              }
              nota={
                cobertura.isError
                  ? 'No se pudo consultar la cobertura'
                  : 'Todo el registro del periodo'
              }
            />
            <MetricTile
              etiqueta="Con PDF guardado"
              valor={
                cobertura.data ? `${cobertura.data.con_pdf} / ${cobertura.data.total}` : '—'
              }
              nota={
                cobertura.isError
                  ? 'No se pudo consultar la cobertura'
                  : 'Todo el registro del periodo'
              }
            />
          </div>

          <div className={layout.fila}>
            <Button
              variante="primario"
              onClick={() => {
                setExtraccion(null);
                setDialogoExtraccion(true);
              }}
              cargando={extraer.isPending}
              disabled={jobActivo !== undefined}
            >
              Completar con GLOSA
            </Button>
            <span className={layout.textoSecundario}>
              Sobre {libro}. Cambia de libro en la cabecera.
            </span>
          </div>

          {jobActivo ? (
            <ProgressBar
              etiqueta={`${presentarTipoJob(jobActivo.tipo)} (${libro})`}
              actual={jobActivo.progreso.actual}
              total={jobActivo.progreso.total}
              porcentaje={jobActivo.progreso.porcentaje}
              mensaje={jobActivo.progreso.mensaje || presentarEstadoJob(jobActivo.estado).texto}
            />
          ) : null}

          {otroLibro ? (
            <p className={layout.textoSecundario}>
              También hay una extracción de {otroLibro.libro} en curso para este periodo. Corren
              de una en una: la sesión SOL es única por empresa.
            </p>
          ) : null}
        </Panel>

        {extraccion ? (
          <Panel
            titulo="Resultado de la última corrida"
            descripcion="Resultado de esta ejecución; los totales del periodo se muestran arriba."
          >
            {extraccion.procesados === 0 ? (
              <p className={layout.textoSecundario}>
                No había comprobantes pendientes para procesar. Se conservan las glosas, los
                detalles y los PDFs guardados anteriormente.
              </p>
            ) : (
              <div className={layout.rejillaMetricas}>
                {extraccion ? (
                  <>
                    <MetricTile
                      etiqueta="Con detalle en esta tanda"
                      valor={`${formatearEntero(extraccion.con_detalle)} / ${formatearEntero(extraccion.procesados)}`}
                      nota={
                        extraccion.pendientes > 0
                          ? `${formatearEntero(extraccion.pendientes)} quedaron para otra vuelta`
                          : 'Incluye los detalles guardados anteriormente'
                      }
                    />
                    <MetricTile
                      etiqueta="PDF nuevos descargados"
                      valor={`${formatearEntero(extraccion.descargados_pdf)} / ${formatearEntero(extraccion.procesados)}`}
                      nota={
                        extraccion.sin_pdf > 0
                          ? `${formatearEntero(extraccion.sin_pdf)} sin PDF; se reintentan en la próxima corrida`
                          : 'Los PDFs ya guardados no se descargan de nuevo'
                      }
                    />
                  </>
                ) : null}
              </div>
            )}
          </Panel>
        ) : null}

        {libro === 'compras' ? (
          <NpdPanel
            ruc={ruc}
            periodo={periodo}
            acciones={<DescargarDetraccionesButton ruc={ruc} periodo={periodo} />}
          />
        ) : null}

        <div ref={listadoRef} tabIndex={-1} className={estilos.destinoListado}>
          <Panel titulo="Listado">
            <div role="group" aria-label="Vista de comprobantes">
              <Button
                pequeno
                aria-pressed={verIncompletos}
                onClick={() => {
                  setVerIncompletos(true);
                  setVerAnulados(false);
                }}
              >
                Incompletos ({incompletos.data?.length ?? 0})
              </Button>
              <Button
                pequeno
                aria-pressed={!verAnulados && !verIncompletos}
                onClick={() => {
                  setVerAnulados(false);
                  setVerIncompletos(false);
                }}
              >
                Todos
              </Button>
              <Button
                pequeno
                aria-pressed={verAnulados}
                onClick={() => {
                  setVerAnulados(true);
                  setVerIncompletos(false);
                }}
              >
                Anulados ({anulados.data?.length ?? 0})
              </Button>
            </div>
            {verAnulados && anulados.isError ? (
              <p role="alert">No se pudieron cargar los anulados de SUNAT.</p>
            ) : null}
            {verIncompletos && incompletos.isError ? (
              <p role="alert">No se pudieron cargar los incompletos.</p>
            ) : null}
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
                  leyenda={`Comprobantes de ${libro} del periodo ${formatearPeriodo(periodo)}`}
                  leyendaOculta
                  columnas={columnas}
                  filas={filas}
                  claveDeFila={(fila) => fila.serie_numero}
                  vacio={
                    <EmptyState
                      titulo={
                        verIncompletos
                          ? 'Sin comprobantes incompletos'
                          : verAnulados
                            ? 'Sin descripciones de anulados'
                            : 'Este periodo no tiene comprobantes'
                      }
                      texto={
                        verIncompletos
                          ? 'No hay campos pendientes de completar en los comprobantes consultados.'
                          : verAnulados
                            ? 'No se encontraron descripciones de anulados en los detalles obtenidos de SUNAT.'
                            : 'Sincroniza la propuesta del SIRE desde la pantalla de periodos para traerlos.'
                      }
                      accion={
                        verAnulados || verIncompletos ? undefined : (
                          <Link to="/periodos">Ir a periodos</Link>
                        )
                      }
                    />
                  }
                />
                {filas.length > 0 && !verAnulados && !verIncompletos ? (
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
      </div>

      <DialogComprobante
        ruc={ruc}
        periodo={periodo}
        serieNumero={abierto}
        onCerrar={() => setParametros({}, { replace: true })}
      />

      <Dialog
        abierto={dialogoExtraccion}
        titulo="Completar con GLOSA"
        texto={`Sobre ${libro}. Obtiene el detalle, la glosa y el PDF desde SOL.${libro === 'ventas' ? ' También consulta los datos de Contraparte y RUC / Doc. que falten en SIRE y aún no se hayan consultado en SOL. Si tampoco aparecen en el comprobante, quedan vacíos.' : ''}`}
        onCerrar={() => setDialogoExtraccion(false)}
        acciones={
          <>
            <Button variante="fantasma" onClick={() => setDialogoExtraccion(false)}>
              Cancelar
            </Button>
            <Button
              variante="primario"
              cargando={extraer.isPending}
              disabled={jobActivo !== undefined || extraer.isPending}
              onClick={() => extraer.mutate()}
            >
              Iniciar proceso
            </Button>
          </>
        }
      >
        <div className={layout.pila}>
          {extraer.isPending ? (
            <p className={layout.textoSecundario} role="status" aria-live="polite">
              El proceso puede tardar varios minutos según el número de comprobantes. El avance
              se ve en el panel «Procesar el periodo»; no cierres esta pestaña.
            </p>
          ) : null}
        </div>
      </Dialog>
    </>
  );
}
