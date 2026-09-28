import { useMutation, useQueryClient } from '@tanstack/react-query';

import { reintentarJob } from '@/api/jobs';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { ErrorState } from '@/components/ui/Feedback';
import { useToast } from '@/hooks/useToast';
import { formatearFechaHora, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { JobResponse } from '@/types/api';

import { describirReintento, presentarEstadoJob, presentarTipoJob } from './estadoJob';

interface Props {
  job: JobResponse | null;
  onCerrar: () => void;
  /** Nombre de la empresa, cuando el historial mezcla varias. */
  empresa?: string;
}

/**
 * Detalle de un trabajo en segundo plano: estado, intentos, errores de cada
 * intento y el resultado tal cual lo guardó el backend. Un trabajo de la cola
 * que quedó fallido se puede volver a encolar desde aquí.
 */
export function DetalleJobDialog({ job, onCerrar, empresa }: Props) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const reintentar = useMutation({
    mutationFn: (jobId: string) => reintentarJob(jobId),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Trabajo en cola otra vez' });
      await Promise.all([
        cliente.invalidateQueries({ queryKey: ['jobs'] }),
        cliente.invalidateQueries({ queryKey: ['resumen-empresas'] }),
        cliente.invalidateQueries({ queryKey: ['solicitudes'] }),
      ]);
      onCerrar();
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo reintentar',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  const periodo = job?.periodo ? ` · ${formatearPeriodo(job.periodo)}` : '';
  const reintento = job ? describirReintento(job) : null;
  const historial = job?.historial_errores ?? [];
  const reintentable = job?.gestionado && job.estado === 'fallido';

  return (
    <Dialog
      abierto={job !== null}
      titulo={job ? `${presentarTipoJob(job.tipo)}${periodo}` : ''}
      onCerrar={onCerrar}
      ancho="amplio"
      acciones={
        <>
          {reintentable && job ? (
            <Button
              variante="primario"
              cargando={reintentar.isPending}
              onClick={() => reintentar.mutate(job.job_id)}
            >
              Reintentar
            </Button>
          ) : null}
          <Button variante="fantasma" onClick={onCerrar}>
            Cerrar
          </Button>
        </>
      }
    >
      {job ? (
        <div className={layout.pila}>
          <dl className={layout.definiciones}>
            {empresa ? (
              <div>
                <dt className={layout.termino}>Empresa</dt>
                <dd className={layout.descripcion}>{empresa}</dd>
              </div>
            ) : null}
            <div>
              <dt className={layout.termino}>Identificador</dt>
              <dd className={layout.descripcion}>{job.job_id}</dd>
            </div>
            <div>
              <dt className={layout.termino}>Estado</dt>
              <dd className={layout.descripcion}>
                {presentarEstadoJob(job.estado).texto}
                {reintento ? ` · ${reintento}` : ''}
              </dd>
            </div>
            <div>
              <dt className={layout.termino}>Creado</dt>
              <dd className={layout.descripcion}>{formatearFechaHora(job.creado_en)}</dd>
            </div>
            <div>
              <dt className={layout.termino}>Actualizado</dt>
              <dd className={layout.descripcion}>{formatearFechaHora(job.actualizado_en)}</dd>
            </div>
            {job.gestionado ? (
              <div>
                <dt className={layout.termino}>Intentos</dt>
                <dd className={layout.descripcion}>
                  {job.intentos ?? 0} de {job.max_intentos ?? 1}
                </dd>
              </div>
            ) : null}
            {job.ultimo_intento_en ? (
              <div>
                <dt className={layout.termino}>Último intento</dt>
                <dd className={layout.descripcion}>
                  {formatearFechaHora(job.ultimo_intento_en)}
                </dd>
              </div>
            ) : null}
            {job.estado === 'pendiente' &&
            job.siguiente_intento_en &&
            (job.intentos ?? 0) > 0 ? (
              <div>
                <dt className={layout.termino}>Próximo intento</dt>
                <dd className={layout.descripcion}>
                  {formatearFechaHora(job.siguiente_intento_en)}
                </dd>
              </div>
            ) : null}
          </dl>

          {job.error ? (
            <ErrorState
              titulo={
                job.estado === 'fallido'
                  ? 'El trabajo terminó con error'
                  : 'El último intento falló'
              }
              texto={job.error}
            />
          ) : null}

          {historial.length > 1 ? (
            <div>
              <h3 className={layout.termino}>Errores por intento</h3>
              <ol>
                {historial.map((registro, i) => (
                  <li key={`${registro.intento ?? i}-${registro.en ?? i}`}>
                    <span className={layout.textoSecundario}>
                      {registro.intento ? `Intento ${registro.intento}` : 'Reinicio'} ·{' '}
                      {formatearFechaHora(registro.en)}:
                    </span>{' '}
                    {registro.error}
                  </li>
                ))}
              </ol>
            </div>
          ) : null}

          {job.resultado ? (
            <pre className={layout.preformateado}>{JSON.stringify(job.resultado, null, 2)}</pre>
          ) : null}
        </div>
      ) : null}
    </Dialog>
  );
}
