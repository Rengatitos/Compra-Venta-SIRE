import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import {
  clasificarComprobante,
  iniciarClasificacion,
  obtenerEstadoClasificador,
} from '@/api/clasificacion';
import { obtenerJob } from '@/api/jobs';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { MetricTile } from '@/components/ui/Feedback';
import { Panel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/Progress';
import { presentarEstadoJob } from '@/features/jobs/estadoJob';
import { useJobs } from '@/features/jobs/useJobs';
import { useToast } from '@/hooks/useToast';
import { formatearEntero, formatearFechaHora } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type {
  ComprobanteResponse,
  CuentaClasificada,
  JobResponse,
  ResultadoClasificacion,
} from '@/types/api';
import type { Libro } from '@/types/domain';

import { Dato, Seccion } from './Seccion';

export const TIPO_JOB_CLASIFICACION = 'clasificacion_cuentas';

function textoCuenta(cuenta: CuentaClasificada | null | undefined): string {
  if (!cuenta) return '—';
  return cuenta.descripcion ? `${cuenta.codigo} · ${cuenta.descripcion}` : cuenta.codigo;
}

function mensajeDeFallo(fallo: unknown): string {
  if (fallo instanceof ApiError && fallo.esLimiteDeTasa) {
    return 'Se alcanzó el límite de solicitudes. Espera un momento.';
  }
  return fallo instanceof Error ? fallo.message : 'Error inesperado.';
}

/** Celda «Cuenta» del listado: código de la cuenta base y si hay que revisarla. */
export function CuentaCelda({ fila }: { fila: ComprobanteResponse }) {
  const clasificacion = fila.clasificacion_contable;
  if (!clasificacion) return <>—</>;
  const codigo = clasificacion.cuenta_base?.codigo;
  return (
    <div className={layout.fila} title={textoCuenta(clasificacion.cuenta_base)}>
      {codigo ? <span>{codigo}</span> : <span>Sin cuenta</span>}
      {clasificacion.requiere_revision ? <Badge tono="aviso">Revisar</Badge> : null}
    </div>
  );
}

/** Bloque de la ficha del comprobante con su clasificación y el botón para (re)clasificarlo. */
export function SeccionClasificacion({
  datos,
  ruc,
  periodo,
}: {
  datos: ComprobanteResponse;
  ruc: string;
  periodo: string;
}) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const clasificacion = datos.clasificacion_contable;
  const libro: Libro = datos.libro === 'ventas' ? 'ventas' : 'compras';

  const clasificar = useMutation({
    mutationFn: () => clasificarComprobante(ruc, periodo, datos.serie_numero, libro),
    onSuccess: async (resultado) => {
      mostrar({
        tono: resultado.requiere_revision ? 'neutro' : 'exito',
        titulo: resultado.cuenta_base
          ? `Cuenta ${resultado.cuenta_base.codigo}`
          : 'Sin cuenta base suficiente',
        detalle: resultado.requiere_revision
          ? 'Requiere revisión: no se escribirá en el Excel de Contasis.'
          : undefined,
      });
      await cliente.invalidateQueries({
        queryKey: ['comprobante', ruc, periodo, datos.serie_numero],
      });
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
    },
    onError: (fallo) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudo clasificar',
        detalle: mensajeDeFallo(fallo),
      }),
  });

  return (
    <Seccion
      titulo="Clasificación contable"
      acciones={
        <div className={layout.fila}>
          {clasificacion ? (
            <Badge tono={clasificacion.requiere_revision ? 'aviso' : 'exito'} conPunto>
              {clasificacion.requiere_revision ? 'Requiere revisión' : 'Lista para Contasis'}
            </Badge>
          ) : null}
          <Button pequeno onClick={() => clasificar.mutate()} cargando={clasificar.isPending}>
            {clasificacion ? 'Volver a clasificar' : 'Clasificar'}
          </Button>
        </div>
      }
    >
      {clasificacion ? (
        <dl className={layout.definiciones}>
          <Dato termino="Cuenta base">{textoCuenta(clasificacion.cuenta_base)}</Dato>
          <Dato termino="Cuenta total">{textoCuenta(clasificacion.cuenta_total)}</Dato>
          <Dato termino="Clasificación">
            {[clasificacion.clasificacion, clasificacion.subtipo].filter(Boolean).join(' · ') ||
              '—'}
          </Dato>
          <Dato termino="Condición IGV">{clasificacion.condicion_igv || '—'}</Dato>
          <Dato termino="Confianza">{Math.round(clasificacion.confianza * 100)} %</Dato>
          <Dato termino="Clasificado">
            {formatearFechaHora(clasificacion.clasificado_en)} · {clasificacion.modelo || '—'}
          </Dato>
          <Dato termino="Motivo">{clasificacion.razon || '—'}</Dato>
        </dl>
      ) : (
        <p className={layout.textoSecundario}>
          Aún sin clasificar. La cuenta sale de los ítems (o la glosa), los importes y las
          actividades económicas (CIIU) de la empresa y de la contraparte.
        </p>
      )}
    </Seccion>
  );
}

/** Panel del periodo para lanzar la clasificación de todo el libro y seguir su avance. */
export function ClasificacionPanel({
  ruc,
  periodo,
  libro,
}: {
  ruc: string;
  periodo: string;
  libro: Libro;
}) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();
  const { seguidos, porId, seguir } = useJobs();
  const [resultado, setResultado] = useState<ResultadoClasificacion | null>(null);

  const estadoMotor = useQuery({
    queryKey: ['clasificador', 'estado'],
    queryFn: obtenerEstadoClasificador,
    staleTime: 60_000,
  });
  const deshabilitado = estadoMotor.data?.habilitado === false;

  const jobActivo = seguidos
    .map((jobId) => porId[jobId])
    .find(
      (job): job is JobResponse =>
        job !== undefined &&
        job.tipo === TIPO_JOB_CLASIFICACION &&
        job.periodo === periodo &&
        job.libro === libro &&
        job.estado !== 'completado' &&
        job.estado !== 'fallido',
    );

  const lanzar = useMutation({
    mutationFn: async (reclasificar: boolean) => {
      setResultado(null);
      const aceptado = await iniciarClasificacion(ruc, periodo, libro, reclasificar);
      seguir(aceptado.job_id);
      for (;;) {
        const job = await obtenerJob(aceptado.job_id);
        if (job.estado === 'fallido') {
          throw new Error(job.error || 'La clasificación no se completó.');
        }
        if (job.estado === 'completado') {
          setResultado((job.resultado as ResultadoClasificacion | null) ?? null);
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
      }
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
    },
    onSuccess: () => mostrar({ tono: 'exito', titulo: 'Clasificación contable completada' }),
    onError: (fallo) =>
      mostrar({
        tono: 'error',
        titulo: 'La clasificación no se completó',
        detalle: mensajeDeFallo(fallo),
      }),
  });

  const ocupado = lanzar.isPending || jobActivo !== undefined;

  return (
    <Panel
      titulo="Clasificación contable"
      descripcion="Asigna la cuenta base con RAG sobre el PCGE y el plan CONTASIS, y Gemini. Solo clasifica los comprobantes «Con glosa»: los demás esperan a que se complete con GLOSA. Solo las cuentas que no requieren revisión pasan al Excel de Contasis."
    >
      {deshabilitado ? (
        <p className={layout.textoSecundario} role="status">
          El clasificador está deshabilitado en el servidor (CLASIFICADOR_HABILITADO).
        </p>
      ) : null}
      {estadoMotor.data?.estado === 'error' ? (
        <p role="alert">El clasificador no pudo iniciar: {estadoMotor.data.error}</p>
      ) : null}

      <div className={layout.fila}>
        <Button
          variante="primario"
          onClick={() => lanzar.mutate(false)}
          cargando={lanzar.isPending && !lanzar.variables}
          disabled={ocupado || deshabilitado}
        >
          Clasificar cuentas
        </Button>
        <Button
          variante="fantasma"
          onClick={() => lanzar.mutate(true)}
          cargando={lanzar.isPending && lanzar.variables === true}
          disabled={ocupado || deshabilitado}
          title="Vuelve a clasificar también los que ya tienen cuenta"
        >
          Reclasificar todo
        </Button>
      </div>

      {jobActivo ? (
        <ProgressBar
          etiqueta={`Clasificación contable (${libro})`}
          actual={jobActivo.progreso.actual}
          total={jobActivo.progreso.total}
          porcentaje={jobActivo.progreso.porcentaje}
          mensaje={jobActivo.progreso.mensaje || presentarEstadoJob(jobActivo.estado).texto}
        />
      ) : null}

      {resultado ? (
        <div className={layout.rejillaMetricas}>
          <MetricTile
            etiqueta="Clasificados"
            valor={formatearEntero(resultado.clasificados)}
            nota={
              resultado.pendientes_restantes > 0
                ? `${formatearEntero(resultado.pendientes_restantes)} quedaron para otra vuelta`
                : 'Sin pendientes en el libro'
            }
          />
          <MetricTile
            etiqueta="Requieren revisión"
            valor={formatearEntero(resultado.requieren_revision)}
            nota="No se escriben en el Excel hasta revisarlos"
          />
          <MetricTile
            etiqueta="Sin clasificar"
            valor={formatearEntero(resultado.sin_glosa_omitidos + resultado.errores)}
            nota={`${formatearEntero(resultado.sin_glosa_omitidos)} omitidos por no tener glosa · ${formatearEntero(resultado.errores)} con error`}
          />
        </div>
      ) : null}
    </Panel>
  );
}
