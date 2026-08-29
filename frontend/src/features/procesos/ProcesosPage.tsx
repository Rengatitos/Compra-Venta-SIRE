import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';

import { listarJobs } from '@/api/jobs';
import { listarPeriodos } from '@/api/periodos';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable, TableFooter } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { SelectField } from '@/components/ui/Field';
import type { Opcion } from '@/components/ui/Field';
import { Pagination } from '@/components/ui/Pagination';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { presentarEstadoJob, presentarTipoJob } from '@/features/jobs/estadoJob';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { formatearFechaHora, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { JobResponse } from '@/types/api';
import type { EstadoJob } from '@/types/domain';

const POR_PAGINA = 25;

const ESTADOS: readonly Opcion[] = [
  { valor: '', texto: 'Todos' },
  { valor: 'pendiente', texto: 'En cola' },
  { valor: 'en_progreso', texto: 'En progreso' },
  { valor: 'completado', texto: 'Completado' },
  { valor: 'fallido', texto: 'Fallido' },
];

export function ProcesosPage() {
  useDocumentTitle('Procesos');

  const ruc = useRuc();

  const [periodo, setPeriodo] = useState('');
  const [estado, setEstado] = useState('');
  const [pagina, setPagina] = useState(1);
  const [aInspeccionar, setAInspeccionar] = useState<JobResponse | null>(null);

  const periodos = useQuery({
    queryKey: ['periodos', ruc],
    queryFn: () => listarPeriodos(ruc),
  });

  const jobs = useQuery({
    queryKey: ['jobs', ruc, { periodo, estado, pagina }],
    queryFn: () =>
      listarJobs({
        periodo: periodo || undefined,
        estado: (estado || undefined) as EstadoJob | undefined,
        limit: POR_PAGINA,
        skip: (pagina - 1) * POR_PAGINA,
      }),
  });

  const filas = jobs.data ?? [];

  const opcionesPeriodo: readonly Opcion[] = [
    { valor: '', texto: 'Todos' },
    ...(periodos.data ?? []).map((fila) => ({
      valor: fila.periodo,
      texto: formatearPeriodo(fila.periodo),
    })),
  ];

  const columnas: readonly Columna<JobResponse>[] = [
    {
      clave: 'proceso',
      cabecera: 'Proceso',
      cabeceraDeFila: true,
      render: (fila) => (
        <>
          <span>{presentarTipoJob(fila.tipo)}</span>
          <br />
          <span className={layout.textoSecundario}>{fila.job_id}</span>
        </>
      ),
    },
    {
      clave: 'periodo',
      cabecera: 'Periodo',
      monoespaciada: true,
      render: (fila) => (
        <Link to={`/periodos/${encodeURIComponent(fila.periodo)}`}>
          {formatearPeriodo(fila.periodo)}
        </Link>
      ),
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (fila) => {
        const presentacion = presentarEstadoJob(fila.estado);
        return (
          <Badge tono={presentacion.tono} conPunto>
            {presentacion.texto}
          </Badge>
        );
      },
    },
    {
      clave: 'avance',
      cabecera: 'Avance',
      numerica: true,
      render: (fila) =>
        fila.progreso.total > 0
          ? `${fila.progreso.actual} / ${fila.progreso.total}`
          : '—',
    },
    {
      clave: 'creado_en',
      cabecera: 'Creado',
      monoespaciada: true,
      render: (fila) => formatearFechaHora(fila.creado_en),
    },
    {
      clave: 'actualizado_en',
      cabecera: 'Actualizado',
      monoespaciada: true,
      render: (fila) => formatearFechaHora(fila.actualizado_en),
    },
    {
      clave: 'acciones',
      cabecera: 'Acciones',
      render: (fila) => (
        <Button pequeno variante="fantasma" onClick={() => setAInspeccionar(fila)}>
          Ver detalle
        </Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        titulo="Procesos"
        descripcion="Historial de los trabajos en segundo plano de esta empresa. La extracción de detalle hace scraping del portal SOL, así que corre fuera de la petición y deja aquí su rastro."
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Historial"
          descripcion="Ordenado del más reciente al más antiguo."
          acciones={
            <>
              <SelectField
                etiqueta="Periodo"
                value={periodo}
                onChange={(evento) => {
                  setPeriodo(evento.target.value);
                  setPagina(1);
                }}
                opciones={opcionesPeriodo}
              />
              <SelectField
                etiqueta="Estado"
                value={estado}
                onChange={(evento) => {
                  setEstado(evento.target.value);
                  setPagina(1);
                }}
                opciones={ESTADOS}
              />
            </>
          }
        >
          {jobs.isPending ? <Skeleton lineas={5} etiqueta="Cargando procesos" /> : null}

          {jobs.isError ? (
            <ErrorState
              titulo="No se pudieron cargar los procesos"
              texto={jobs.error instanceof ApiError ? jobs.error.message : 'Error inesperado.'}
              accion={
                <Button pequeno onClick={() => void jobs.refetch()}>
                  Reintentar
                </Button>
              }
            />
          ) : null}

          {jobs.data ? (
            <>
              <DataTable
                leyenda="Trabajos en segundo plano de esta empresa"
                leyendaOculta
                columnas={columnas}
                filas={filas}
                claveDeFila={(fila) => fila.job_id}
                vacio={
                  <EmptyState
                    titulo="Todavía no hay procesos"
                    texto="Lanza una extracción de detalle desde la pantalla de un periodo y aparecerá aquí."
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

      <Dialog
        abierto={aInspeccionar !== null}
        titulo={
          aInspeccionar
            ? `${presentarTipoJob(aInspeccionar.tipo)} · ${formatearPeriodo(aInspeccionar.periodo)}`
            : ''
        }
        onCerrar={() => setAInspeccionar(null)}
        acciones={
          <Button variante="fantasma" onClick={() => setAInspeccionar(null)}>
            Cerrar
          </Button>
        }
      >
        {aInspeccionar ? (
          <div className={layout.pila}>
            <dl className={layout.definiciones}>
              <div>
                <dt className={layout.termino}>Identificador</dt>
                <dd className={layout.descripcion}>{aInspeccionar.job_id}</dd>
              </div>
              <div>
                <dt className={layout.termino}>Estado</dt>
                <dd className={layout.descripcion}>
                  {presentarEstadoJob(aInspeccionar.estado).texto}
                </dd>
              </div>
              <div>
                <dt className={layout.termino}>Creado</dt>
                <dd className={layout.descripcion}>
                  {formatearFechaHora(aInspeccionar.creado_en)}
                </dd>
              </div>
              <div>
                <dt className={layout.termino}>Actualizado</dt>
                <dd className={layout.descripcion}>
                  {formatearFechaHora(aInspeccionar.actualizado_en)}
                </dd>
              </div>
            </dl>

            {aInspeccionar.error ? (
              <ErrorState titulo="El trabajo terminó con error" texto={aInspeccionar.error} />
            ) : null}

            {aInspeccionar.resultado ? (
              <pre className={layout.preformateado}>
                {JSON.stringify(aInspeccionar.resultado, null, 2)}
              </pre>
            ) : null}
          </div>
        ) : null}
      </Dialog>
    </>
  );
}
