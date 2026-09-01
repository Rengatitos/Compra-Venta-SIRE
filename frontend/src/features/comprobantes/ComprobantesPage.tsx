import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { ChangeEvent } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';

import { ejecutarAnalisis } from '@/api/analisis';
import { exportarLote, listarComprobantes } from '@/api/comprobantes';
import { iniciarExtraccionDetalle } from '@/api/detalle';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { DataTable, TableFooter } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, MetricTile, Skeleton } from '@/components/ui/Feedback';
import { FileField, SelectField } from '@/components/ui/Field';
import { Pagination } from '@/components/ui/Pagination';
import { Panel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/Progress';
import { useRuc } from '@/features/auth/useAuth';
import { presentarEstadoJob } from '@/features/jobs/estadoJob';
import { useJobs } from '@/features/jobs/useJobs';
import { NoEncontradaPage } from '@/features/shared/NoEncontradaPage';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import {
  formatearEntero,
  formatearFecha,
  formatearMoneda,
  formatearPeriodo,
} from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ComprobanteResponse, ResultadoAnalisis } from '@/types/api';
import type { FormatoExport, Libro } from '@/types/domain';
import { ESTADOS_JOB_TERMINALES, esPeriodoValido } from '@/types/domain';

import { DialogComprobante } from './DialogComprobante';
import { presentarEstadoComprobante, presentarResultadoIA } from './estadoComprobante';

const POR_PAGINA = 100;

/**
 * El Excel sigue la plantilla de Contasis, que tiene una hoja por libro: hay una
 * descarga por libro, más el PDF (el único que lleva el análisis IA).
 */
type Descarga = 'excel:compras' | 'excel:ventas' | 'pdf';

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
  const [exportando, setExportando] = useState<Descarga | null>(null);
  const [dialogoAnalisis, setDialogoAnalisis] = useState(false);
  const [archivos, setArchivos] = useState<File[]>([]);
  const [errorArchivos, setErrorArchivos] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoAnalisis | null>(null);

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
  const jobActivo = seguidos
    .map((jobId) => porId[jobId])
    .find(
      (job) =>
        job !== undefined &&
        job.periodo === periodo &&
        !ESTADOS_JOB_TERMINALES.includes(job.estado),
    );

  const extraer = useMutation({
    mutationFn: () => iniciarExtraccionDetalle(ruc, periodo),
    onSuccess: (aceptado) => {
      seguir(aceptado.job_id);
      // `aceptado.mensaje` apunta al endpoint de la API, que no le sirve a
      // nadie mirando la pantalla. El avance sale en la barra de aquí abajo y
      // queda registrado en Procesos.
      mostrar({
        tono: 'exito',
        titulo: 'Extracción iniciada',
        detalle: 'El avance aparece en esta misma página mientras corre.',
        accion: { texto: 'Ver en Procesos', a: '/procesos' },
      });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo iniciar la extracción',
        detalle:
          fallo instanceof ApiError && fallo.esLimiteDeTasa
            ? 'La extracción admite 5 arranques por minuto. Espera un momento.'
            : fallo instanceof ApiError
              ? fallo.message
              : 'Error inesperado.',
      });
    },
  });

  const analizar = useMutation({
    mutationFn: () => ejecutarAnalisis(ruc, periodo, archivos),
    onSuccess: async (respuesta) => {
      setResultado(respuesta.datos);
      setDialogoAnalisis(false);
      mostrar({
        tono: 'exito',
        titulo: respuesta.mensaje ?? 'Análisis completado',
        detalle: respuesta.datos
          ? `${respuesta.datos.procesadas} de ${respuesta.datos.total_encontradas} comprobantes procesados.`
          : undefined,
      });
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'El análisis no se completó',
        detalle:
          fallo instanceof ApiError && fallo.esLimiteDeTasa
            ? 'El análisis admite 5 ejecuciones por minuto. Espera un momento.'
            : fallo instanceof ApiError
              ? fallo.message
              : 'Error inesperado.',
      });
    },
  });

  if (!esPeriodoValido(periodo)) return <NoEncontradaPage />;

  async function exportar(descarga: Descarga, formato: FormatoExport, libroPedido?: Libro) {
    setExportando(descarga);
    try {
      await exportarLote(ruc, periodo, formato, libroPedido);
    } catch (fallo) {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo exportar',
        detalle:
          fallo instanceof ApiError && fallo.esNoEncontrado
            ? libroPedido
              ? `El periodo no tiene comprobantes de ${libroPedido} que exportar.`
              : 'El periodo no tiene comprobantes que exportar.'
            : fallo instanceof ApiError
              ? fallo.message
              : 'Error inesperado.',
      });
    } finally {
      setExportando(null);
    }
  }

  function alElegirArchivos(evento: ChangeEvent<HTMLInputElement>) {
    const seleccionados = Array.from(evento.target.files ?? []);
    const pdfs = seleccionados.filter((archivo) => archivo.name.toLowerCase().endsWith('.pdf'));

    setErrorArchivos(
      pdfs.length === seleccionados.length
        ? null
        : 'Solo se aceptan archivos PDF. El backend ignora el resto.',
    );
    setArchivos(pdfs);
  }

  const filas = comprobantes.data ?? [];

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
      clave: 'cuenta_rag',
      cabecera: 'Cuenta RAG',
      monoespaciada: true,
      render: (fila) => fila.analisis?.rag?.cuenta_base ?? '—',
    },
    {
      clave: 'glosa_rag',
      cabecera: 'Glosa',
      anchoMinimo: '16rem',
      render: (fila) => fila.analisis?.rag?.glosa ?? '—',
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
        const resultadoIA = presentarResultadoIA(fila.analisis?.resultado ?? null);
        return (
          <div className={layout.fila}>
            <Badge tono={estado.tono} conPunto>
              {estado.texto}
            </Badge>
            {resultadoIA ? <Badge tono={resultadoIA.tono}>{resultadoIA.texto}</Badge> : null}
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
              onClick={() => void exportar('excel:compras', 'excel', 'compras')}
              cargando={exportando === 'excel:compras'}
              disabled={exportando !== null}
            >
              Registro de compras
            </Button>
            <Button
              onClick={() => void exportar('excel:ventas', 'excel', 'ventas')}
              cargando={exportando === 'excel:ventas'}
              disabled={exportando !== null}
            >
              Registro de ventas
            </Button>
            <Button
              onClick={() => void exportar('pdf', 'pdf')}
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
          descripcion="El proceso consulta cada comprobante en SOL, arma la glosa desde sus ítems y obtiene los códigos contables con RAG. Al terminar, esta vista previa se actualiza y el Excel queda listo."
          acciones={
            <SelectField
              etiqueta="Libro"
              value={libro}
              onChange={(evento) => {
                setLibro(evento.target.value as Libro);
                setPagina(1);
              }}
              opciones={[
                { valor: 'compras', texto: 'Compras (RCE)' },
                { valor: 'ventas', texto: 'Ventas (RVIE) — no disponible', deshabilitada: true },
              ]}
            />
          }
        >
          <div className={layout.fila}>
            <Button
              variante="primario"
              onClick={() => extraer.mutate()}
              cargando={extraer.isPending}
              disabled={jobActivo !== undefined}
            >
              Completar con SUNAT y RAG
            </Button>
            <Button
              onClick={() => {
                setResultado(null);
                setDialogoAnalisis(true);
              }}
              cargando={analizar.isPending}
            >
              Analizar con IA
            </Button>
            <ButtonLink a="/periodos" variante="fantasma">
              Volver a periodos
            </ButtonLink>
          </div>

          {jobActivo ? (
            <ProgressBar
              etiqueta="Avance de la extracción de detalle"
              actual={jobActivo.progreso.actual}
              total={jobActivo.progreso.total}
              porcentaje={jobActivo.progreso.porcentaje}
              mensaje={
                jobActivo.progreso.mensaje || presentarEstadoJob(jobActivo.estado).texto
              }
            />
          ) : null}
        </Panel>

        {resultado ? (
          <Panel
            titulo="Resultado del análisis"
            descripcion="Un fallo en un comprobante concreto no detiene la corrida: queda marcado como error de análisis y se cuenta aparte."
          >
            <div className={layout.rejillaMetricas}>
              <MetricTile
                etiqueta="Encontrados"
                valor={formatearEntero(resultado.total_encontradas)}
                nota="Comprobantes pendientes de análisis"
              />
              <MetricTile
                etiqueta="Procesados"
                valor={formatearEntero(resultado.procesadas)}
                nota="Clasificados correctamente"
              />
              <MetricTile
                etiqueta="Errores"
                valor={formatearEntero(resultado.errores)}
                nota="Se pueden reintentar"
              />
              <MetricTile
                etiqueta="Sin datos"
                valor={formatearEntero(resultado.sin_datos)}
                nota="La IA no encontró información suficiente"
              />
            </div>
          </Panel>
        ) : null}

        <Panel titulo="Listado">
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

      <DialogComprobante
        ruc={ruc}
        periodo={periodo}
        serieNumero={abierto}
        onCerrar={() => setParametros({}, { replace: true })}
      />

      <Dialog
        abierto={dialogoAnalisis}
        titulo="Analizar con IA"
        texto="Clasifica con Gemini todos los comprobantes del periodo que estén pendientes de análisis o que fallaron en un intento anterior."
        onCerrar={() => setDialogoAnalisis(false)}
        acciones={
          <>
            <Button variante="fantasma" onClick={() => setDialogoAnalisis(false)}>
              Cancelar
            </Button>
            <Button
              variante="primario"
              cargando={analizar.isPending}
              onClick={() => analizar.mutate()}
            >
              Ejecutar análisis
            </Button>
          </>
        }
      >
        <div className={layout.pila}>
          <FileField
            etiqueta="PDFs de contexto (opcional)"
            name="archivos"
            accept="application/pdf"
            multiple
            onChange={alElegirArchivos}
            error={errorArchivos}
            ayuda={
              archivos.length > 0
                ? `${archivos.length} PDF(s) listos para esta corrida.`
                : 'Se indexan solo para esta corrida. Sin adjuntos se usa el contexto permanente de la empresa.'
            }
          />

          <p className={layout.textoSecundario}>
            El rubro que orienta la clasificación no se elige aquí: se deduce del CIIU dentro
            del token de SUNAT guardado en la empresa.
          </p>

          {analizar.isPending ? (
            <p className={layout.textoSecundario} role="status" aria-live="polite">
              El análisis es sincrónico y puede tardar varios minutos según el número de
              comprobantes. No cierres esta pestaña.
            </p>
          ) : null}
        </div>
      </Dialog>
    </>
  );
}
