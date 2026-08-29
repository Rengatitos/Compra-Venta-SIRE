import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { useJobPolling } from '@/hooks/useJobPolling';
import { useToast } from '@/hooks/useToast';
import { formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import type { JobResponse } from '@/types/api';
import { ESTADOS_JOB_TERMINALES } from '@/types/domain';

import { ContextoJobsReact } from './jobsContext';
import { presentarTipoJob } from './estadoJob';

/**
 * Misma convención que `sire.sesion` y `sire.tema`. Es `sessionStorage` porque
 * un job pertenece a la sesión que lo lanzó: el historial completo, que sí
 * sobrevive a todo, vive en el backend (`GET /jobs`).
 */
const CLAVE = 'sire.jobs';

/** Tope de ids seguidos a la vez, para no dejar sondeos colgando sin límite. */
const MAXIMO = 10;

function leerAlmacen(): string[] {
  try {
    const crudo = sessionStorage.getItem(CLAVE);
    if (!crudo) return [];
    const dato: unknown = JSON.parse(crudo);
    if (!Array.isArray(dato)) return [];
    return dato.filter((id): id is string => typeof id === 'string').slice(0, MAXIMO);
  } catch {
    // Modo privado, almacenamiento bloqueado o JSON corrupto: se empieza vacío.
    return [];
  }
}

interface PropsSeguidor {
  jobId: string;
  onDatos: (job: JobResponse) => void;
  onDescartar: (jobId: string) => void;
}

/**
 * Un componente por job: `useJobPolling` es un hook y no se puede llamar en
 * bucle desde el proveedor. Solo sondea, no pinta nada.
 */
function SeguidorDeJob({ jobId, onDatos, onDescartar }: PropsSeguidor) {
  const { mostrar } = useToast();
  const cliente = useQueryClient();
  const anunciado = useRef(false);

  const job = useJobPolling(jobId);
  const datos = job.data;

  useEffect(() => {
    if (datos) onDatos(datos);
  }, [datos, onDatos]);

  useEffect(() => {
    if (!datos || anunciado.current) return;
    if (!ESTADOS_JOB_TERMINALES.includes(datos.estado)) return;
    anunciado.current = true;

    const donde = `${presentarTipoJob(datos.tipo)} · ${formatearPeriodo(datos.periodo)}`;

    if (datos.estado === 'fallido') {
      mostrar({ tono: 'error', titulo: `${donde}: falló`, detalle: datos.error ?? undefined });
      return;
    }

    // El detalle de los comprobantes cambió: se refresca la caché aunque el
    // usuario ya no esté en la pantalla del periodo.
    void cliente.invalidateQueries({ queryKey: ['comprobantes', datos.ruc, datos.periodo] });
    void cliente.invalidateQueries({ queryKey: ['comprobante', datos.ruc, datos.periodo] });
    void cliente.invalidateQueries({ queryKey: ['jobs', datos.ruc] });

    mostrar({
      tono: 'exito',
      titulo: `${donde}: completado`,
      detalle: 'Los comprobantes del periodo ya tienen su detalle.',
    });
  }, [datos, mostrar, cliente]);

  // Un job de otra empresa (403) o borrado (404) no se vuelve a consultar.
  const fallo = job.error;
  useEffect(() => {
    if (fallo instanceof ApiError && (fallo.esNoEncontrado || fallo.status === 403)) {
      onDescartar(jobId);
    }
  }, [fallo, jobId, onDescartar]);

  return null;
}

export function JobsProvider({ children }: { children: ReactNode }) {
  const [seguidos, setSeguidos] = useState<string[]>(leerAlmacen);
  const [porId, setPorId] = useState<Record<string, JobResponse>>({});

  useEffect(() => {
    try {
      sessionStorage.setItem(CLAVE, JSON.stringify(seguidos));
    } catch {
      // Sin almacenamiento el seguimiento vive en memoria hasta recargar.
    }
  }, [seguidos]);

  const seguir = useCallback((jobId: string) => {
    setSeguidos((previos) =>
      previos.includes(jobId) ? previos : [jobId, ...previos].slice(0, MAXIMO),
    );
  }, []);

  const dejarDeSeguir = useCallback((jobId: string) => {
    setSeguidos((previos) => previos.filter((id) => id !== jobId));
    setPorId((previos) => {
      if (!(jobId in previos)) return previos;
      const { [jobId]: _descartado, ...resto } = previos;
      return resto;
    });
  }, []);

  const registrarDatos = useCallback((job: JobResponse) => {
    setPorId((previos) =>
      previos[job.job_id] === job ? previos : { ...previos, [job.job_id]: job },
    );
  }, []);

  const valor = useMemo(
    () => ({ seguidos, porId, seguir, dejarDeSeguir }),
    [seguidos, porId, seguir, dejarDeSeguir],
  );

  return (
    <ContextoJobsReact.Provider value={valor}>
      {seguidos.map((jobId) => (
        <SeguidorDeJob
          key={jobId}
          jobId={jobId}
          onDatos={registrarDatos}
          onDescartar={dejarDeSeguir}
        />
      ))}
      {children}
    </ContextoJobsReact.Provider>
  );
}
