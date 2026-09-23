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

/**
 * Jobs cuyo final ya se anunció en esta sesión. Sin esto, cada recarga volvía a
 * ver como recién terminados todos los jobs seguidos —siguen en `sire.jobs`
 * para no perder su avance— y repetía un aviso por cada uno.
 */
const CLAVE_ANUNCIADOS = 'sire.jobs.anunciados';
const MAXIMO_ANUNCIADOS = 50;
/** Un job que terminó hace más de esto ya no se anuncia al recargar. */
const AVISO_RECIENTE_MS = 2 * 60_000;

function leerAnunciados(): string[] {
  try {
    const dato: unknown = JSON.parse(sessionStorage.getItem(CLAVE_ANUNCIADOS) ?? '[]');
    return Array.isArray(dato) ? dato.filter((id): id is string => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

function yaAnunciado(jobId: string): boolean {
  return leerAnunciados().includes(jobId);
}

function marcarAnunciado(jobId: string): void {
  try {
    const previos = leerAnunciados().filter((id) => id !== jobId);
    sessionStorage.setItem(
      CLAVE_ANUNCIADOS,
      JSON.stringify([jobId, ...previos].slice(0, MAXIMO_ANUNCIADOS)),
    );
  } catch {
    // Sin almacenamiento se vuelve a lo de antes: se recuerda solo en memoria.
  }
}

/** Qué cambió al terminar, según el tipo de trabajo. */
const DETALLE_COMPLETADO: Record<string, string> = {
  detracciones:
    'Las detracciones relacionadas ya están disponibles en el listado de comprobantes.',
  clasificacion_cuentas: 'Las cuentas contables ya se ven en el listado de comprobantes.',
  descarga_pdfs: 'Los PDFs de SUNAT ya están guardados.',
};

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
    if (yaAnunciado(jobId)) return;
    marcarAnunciado(jobId);
    // Terminó hace rato, antes de esta carga de la página: no es una novedad.
    const terminadoHace = Date.now() - new Date(datos.actualizado_en).getTime();
    if (terminadoHace > AVISO_RECIENTE_MS) return;

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
      detalle:
        DETALLE_COMPLETADO[datos.tipo] ??
        'La vista previa ya incluye el detalle y la glosa de SUNAT.',
    });
  }, [datos, jobId, mostrar, cliente]);

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
