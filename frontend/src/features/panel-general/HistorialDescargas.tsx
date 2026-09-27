import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { listarJobs } from '@/api/jobs';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { type Columna, DataTable, TableFooter } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { type Opcion, SelectField } from '@/components/ui/Field';
import { Pagination } from '@/components/ui/Pagination';
import { Panel } from '@/components/ui/Panel';
import { DetalleJobDialog } from '@/features/jobs/DetalleJobDialog';
import {
  OPCIONES_ESTADO_JOB,
  OPCIONES_TIPO_JOB,
  describirReintento,
  presentarEstadoJob,
  presentarTipoJob,
} from '@/features/jobs/estadoJob';
import { formatearFechaHora, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { JobResponse } from '@/types/api';
import { ESTADOS_JOB_TERMINALES, type EstadoJob, type TipoJob } from '@/types/domain';

import { ETIQUETA_LIBRO } from './etiquetas';

const POR_PAGINA = 25;
const INTERVALO_MS = 5000;

interface Props {
  /** RUC → nombre, para poner nombre a cada fila y al filtro de empresa. */
  nombres: ReadonlyMap<string, string>;
}

/**
 * Historial de procesos de todas las empresas: descargas SIRE, comprobantes,
 * clasificación, archivos y correos. Se refresca solo mientras alguno de los
 * visibles sigue vivo.
 */
export function HistorialDescargas({ nombres }: Props) {
  const [ruc, setRuc] = useState('');
  const [tipo, setTipo] = useState('');
  const [estado, setEstado] = useState('');
  const [pagina, setPagina] = useState(1);
  const [aInspeccionar, setAInspeccionar] = useState<JobResponse | null>(null);

  const jobs = useQuery({
    queryKey: ['jobs', 'todas', { ruc, tipo, estado, pagina }],
    queryFn: () =>
      listarJobs(ruc || null, {
        tipo: (tipo || undefined) as TipoJob | undefined,
        estado: (estado || undefined) as EstadoJob | undefined,
        limit: POR_PAGINA,
        skip: (pagina - 1) * POR_PAGINA,
      }),
    refetchInterval: (consulta) =>
      consulta.state.data?.some((job) => !ESTADOS_JOB_TERMINALES.includes(job.estado))
        ? INTERVALO_MS
        : false,
  });

  const filas = jobs.data ?? [];
  const opcionesEmpresa: readonly Opcion[] = [
    { valor: '', texto: 'Todas' },
    ...[...nombres].map(([valor, texto]) => ({ valor, texto })),
  ];

  const columnas: readonly Columna<JobResponse>[] = [
    {
      clave: 'fecha',
      cabecera: 'Fecha',
      monoespaciada: true,
      render: (fila) => formatearFechaHora(fila.creado_en),
    },
    {
      clave: 'empresa',
      cabecera: 'Empresa',
      cabeceraDeFila: true,
      anchoMinimo: '12rem',
      render: (fila) => (
        <>
          {/* El ZIP y el correo son de una solicitud entera, no de una empresa. */}
          <span>{fila.ruc ? (nombres.get(fila.ruc) ?? fila.ruc) : 'Solicitud masiva'}</span>
          <br />
          <span className={layout.textoSecundario}>{fila.ruc || 'Varias empresas'}</span>
        </>
      ),
    },
    { clave: 'tipo', cabecera: 'Proceso', render: (fila) => presentarTipoJob(fila.tipo) },
    {
      clave: 'periodo',
      cabecera: 'Periodo · libro',
      render: (fila) =>
        [
          fila.periodo ? formatearPeriodo(fila.periodo) : null,
          fila.libro ? ETIQUETA_LIBRO[fila.libro] : null,
        ]
          .filter(Boolean)
          .join(' · ') || '—',
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (fila) => {
        const presentacion = presentarEstadoJob(fila.estado);
        const reintento = describirReintento(fila);
        return (
          <>
            <Badge tono={presentacion.tono} conPunto>
              {presentacion.texto}
            </Badge>
            {reintento ? (
              <>
                <br />
                <span className={layout.textoSecundario}>{reintento}</span>
              </>
            ) : null}
          </>
        );
      },
    },
    {
      clave: 'detalle',
      cabecera: 'Detalle',
      anchoMinimo: '14rem',
      render: (fila) => (
        <>
          <span className={layout.textoSecundario}>{fila.error ?? fila.progreso.mensaje}</span>
          <br />
          <Button pequeno variante="fantasma" onClick={() => setAInspeccionar(fila)}>
            Ver detalle
          </Button>
        </>
      ),
    },
  ];

  function filtro(poner: (valor: string) => void) {
    return (evento: { target: { value: string } }) => {
      poner(evento.target.value);
      setPagina(1);
    };
  }

  return (
    <Panel
      titulo="Historial de procesos"
      descripcion="Todos los trabajos en segundo plano de todas las empresas, del más reciente al más antiguo."
      acciones={
        <>
          <SelectField
            etiqueta="Empresa"
            value={ruc}
            onChange={filtro(setRuc)}
            opciones={opcionesEmpresa}
          />
          <SelectField
            etiqueta="Proceso"
            value={tipo}
            onChange={filtro(setTipo)}
            opciones={[{ valor: '', texto: 'Todos' }, ...OPCIONES_TIPO_JOB]}
          />
          <SelectField
            etiqueta="Estado"
            value={estado}
            onChange={filtro(setEstado)}
            opciones={[{ valor: '', texto: 'Todos' }, ...OPCIONES_ESTADO_JOB]}
          />
        </>
      }
    >
      {jobs.isPending ? <Skeleton lineas={4} etiqueta="Cargando el historial" /> : null}
      {jobs.isError ? (
        <ErrorState
          titulo="No se pudo cargar el historial"
          texto={jobs.error instanceof ApiError ? jobs.error.message : 'Error inesperado.'}
        />
      ) : null}
      {jobs.data ? (
        <>
          <DataTable
            leyenda="Historial de procesos de todas las empresas"
            leyendaOculta
            columnas={columnas}
            filas={filas}
            claveDeFila={(fila) => fila.job_id}
            vacio={
              <EmptyState
                titulo="Sin procesos"
                texto="Aquí aparecerán las descargas y demás trabajos en segundo plano."
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
      <DetalleJobDialog
        job={aInspeccionar}
        empresa={aInspeccionar ? nombres.get(aInspeccionar.ruc) : undefined}
        onCerrar={() => setAInspeccionar(null)}
      />
    </Panel>
  );
}
