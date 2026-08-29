import { useQuery } from '@tanstack/react-query';
import { useEffect, useId, useRef, useState } from 'react';

import { listarJobs } from '@/api/jobs';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { ProgressBar } from '@/components/ui/Progress';
import { useRuc } from '@/features/auth/useAuth';
import { formatearFechaHora, formatearPeriodo } from '@/lib/format';
import type { JobResponse } from '@/types/api';
import { ESTADOS_JOB_TERMINALES } from '@/types/domain';

import { presentarEstadoJob, presentarTipoJob } from './estadoJob';
import estilos from './NotificacionesMenu.module.css';
import { useJobs } from './useJobs';

/** Cuántas corridas recientes caben en la mirada breve. */
const RECIENTES = 5;

function IconoCampana() {
  return (
    <svg
      className={estilos.icono}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M18 8.5a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16s-2-1.5-2-6.5Z" />
      <path d="M10.3 19a2 2 0 0 0 3.4 0" />
    </svg>
  );
}

function IconoHistorial() {
  return (
    <svg
      className={estilos.iconoPequeno}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1" />
      <path d="M3.5 4.5V9H8" />
      <path d="M12 7.5V12l3 1.8" />
    </svg>
  );
}

interface Fila {
  job: JobResponse;
  /** Solo lo seguido por esta pestaña se puede dejar de seguir. */
  seguido: boolean;
}

/** Combina lo que sigue esta pestaña con lo último que guardó el backend. */
function unir(seguidos: readonly JobResponse[], recientes: readonly JobResponse[]): Fila[] {
  const vistos = new Set(seguidos.map((job) => job.job_id));
  return [
    ...seguidos.map((job) => ({ job, seguido: true })),
    ...recientes.filter((job) => !vistos.has(job.job_id)).map((job) => ({ job, seguido: false })),
  ].slice(0, RECIENTES);
}

export function NotificacionesMenu() {
  const ruc = useRuc();
  const { seguidos, porId, dejarDeSeguir } = useJobs();

  const [abierto, setAbierto] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);
  const idPanel = useId();

  const enSeguimiento = seguidos
    .map((jobId) => porId[jobId])
    .filter((job): job is JobResponse => job !== undefined);

  const activos = enSeguimiento.filter((job) => !ESTADOS_JOB_TERMINALES.includes(job.estado));

  // El historial corto solo se pide con el panel abierto: la campana no debe
  // costar una petición por cada carga de la aplicación.
  const recientes = useQuery({
    queryKey: ['jobs', ruc, { limit: RECIENTES }],
    queryFn: () => listarJobs({ limit: RECIENTES }),
    enabled: abierto,
  });

  const visibles = unir(enSeguimiento, recientes.data ?? []);

  useEffect(() => {
    if (!abierto) return;

    function alPulsarTecla(evento: KeyboardEvent) {
      if (evento.key === 'Escape') setAbierto(false);
    }
    function alPulsarFuera(evento: MouseEvent) {
      if (!contenedor.current?.contains(evento.target as Node)) setAbierto(false);
    }

    document.addEventListener('keydown', alPulsarTecla);
    document.addEventListener('mousedown', alPulsarFuera);
    return () => {
      document.removeEventListener('keydown', alPulsarTecla);
      document.removeEventListener('mousedown', alPulsarFuera);
    };
  }, [abierto]);

  const resumen =
    activos.length > 0
      ? `${activos.length} proceso(s) en curso`
      : 'Sin procesos en curso';

  return (
    <div className={estilos.contenedor} ref={contenedor}>
      <button
        type="button"
        className={estilos.campana}
        aria-label={`Notificaciones. ${resumen}`}
        aria-expanded={abierto}
        aria-controls={idPanel}
        onClick={() => setAbierto((previo) => !previo)}
      >
        <IconoCampana />
        {activos.length > 0 ? <span className={estilos.punto} aria-hidden="true" /> : null}
      </button>

      {/* El estado se anuncia solo cuando cambia, sin depender de abrir el panel. */}
      <span className="visually-hidden" role="status" aria-live="polite">
        {resumen}
      </span>

      {abierto ? (
        <div
          className={estilos.panel}
          id={idPanel}
          role="dialog"
          aria-label="Procesos recientes"
        >
          <p className={estilos.titulo}>Procesos recientes</p>

          {visibles.length === 0 ? (
            <p className={estilos.vacio}>
              {recientes.isPending
                ? 'Consultando los últimos procesos…'
                : 'Todavía no has lanzado ninguna extracción.'}
            </p>
          ) : (
            <ul className={estilos.lista}>
              {visibles.map(({ job, seguido }) => {
                const estado = presentarEstadoJob(job.estado);
                const terminado = ESTADOS_JOB_TERMINALES.includes(job.estado);
                return (
                  <li key={job.job_id} className={estilos.item}>
                    <div className={estilos.cabeceraItem}>
                      <span className={estilos.periodo}>
                        {presentarTipoJob(job.tipo)} · {formatearPeriodo(job.periodo)}
                      </span>
                      <Badge tono={estado.tono} conPunto>
                        {estado.texto}
                      </Badge>
                    </div>
                    {terminado ? (
                      <p className={estilos.marca}>{formatearFechaHora(job.actualizado_en)}</p>
                    ) : (
                      <ProgressBar
                        etiqueta={`Avance de ${presentarTipoJob(job.tipo)}`}
                        actual={job.progreso.actual}
                        total={job.progreso.total}
                        porcentaje={job.progreso.porcentaje}
                        mensaje={job.progreso.mensaje || estado.texto}
                      />
                    )}
                    {seguido ? (
                      <Button
                        pequeno
                        variante="fantasma"
                        onClick={() => dejarDeSeguir(job.job_id)}
                      >
                        {terminado ? 'Quitar del panel' : 'Dejar de seguir'}
                      </Button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}

          <div className={estilos.pie}>
            <ButtonLink a="/procesos" pequeno bloque onClick={() => setAbierto(false)}>
              <IconoHistorial />
              Ver historial de procesos
            </ButtonLink>
          </div>
        </div>
      ) : null}
    </div>
  );
}
