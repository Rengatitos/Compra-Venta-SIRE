import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';

import { iniciarExtraccionDetalle } from '@/api/detalle';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import type { TonoInsignia } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState, ErrorState } from '@/components/ui/Feedback';
import { Panel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/Progress';
import { useRuc } from '@/features/auth/useAuth';
import { NoEncontradaPage } from '@/features/shared/NoEncontradaPage';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useJobPolling } from '@/hooks/useJobPolling';
import { useToast } from '@/hooks/useToast';
import { formatearFechaHora, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { EstadoJob } from '@/types/domain';
import { esPeriodoValido } from '@/types/domain';

const TONO_ESTADO: Record<EstadoJob, TonoInsignia> = {
  pendiente: 'neutro',
  en_progreso: 'info',
  completado: 'exito',
  fallido: 'error',
};

const TEXTO_ESTADO: Record<EstadoJob, string> = {
  pendiente: 'En cola',
  en_progreso: 'En progreso',
  completado: 'Completado',
  fallido: 'Fallido',
};

export function DetallePage() {
  const { periodo = '' } = useParams();
  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [jobId, setJobId] = useState<string | null>(null);

  useDocumentTitle(`Extracción de detalle ${formatearPeriodo(periodo)}`);

  const job = useJobPolling(jobId);

  const iniciar = useMutation({
    mutationFn: () => iniciarExtraccionDetalle(ruc, periodo),
    onSuccess: (aceptado) => {
      setJobId(aceptado.job_id);
      mostrar({ tono: 'exito', titulo: 'Extracción iniciada', detalle: aceptado.mensaje });
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

  // Al terminar el job, el detalle de los comprobantes cambió: se refresca la
  // caché para que el listado y las fichas muestren los ítems nuevos.
  const estado = job.data?.estado;
  useEffect(() => {
    if (estado === 'completado') {
      void cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
      void cliente.invalidateQueries({ queryKey: ['comprobante', ruc, periodo] });
    }
  }, [estado, cliente, ruc, periodo]);

  if (!esPeriodoValido(periodo)) return <NoEncontradaPage />;

  const datos = job.data;

  return (
    <>
      <PageHeader
        titulo="Extracción de detalle desde SUNAT"
        descripcion="Obtiene el detalle de ítems de cada comprobante haciendo scraping del portal SOL, porque la API SIRE no lo expone línea por línea."
        acciones={
          <Button
            variante="primario"
            onClick={() => iniciar.mutate()}
            cargando={iniciar.isPending}
            disabled={estado === 'pendiente' || estado === 'en_progreso'}
          >
            Iniciar extracción
          </Button>
        }
      />

      <div className={layout.pilaAmplia}>
        <Panel
          titulo="Estado del trabajo"
          descripcion="La extracción corre en segundo plano. Esta pantalla consulta su avance cada 3 segundos y deja de consultar en cuanto termina."
          acciones={
            datos ? (
              <Badge tono={TONO_ESTADO[datos.estado]} conPunto>
                {TEXTO_ESTADO[datos.estado]}
              </Badge>
            ) : null
          }
        >
          {!jobId ? (
            <EmptyState
              titulo="Sin extracción en curso"
              texto="Pulsa «Iniciar extracción» para lanzar el scraping de los comprobantes pendientes de este periodo."
            />
          ) : null}

          {datos ? (
            <>
              <ProgressBar
                etiqueta="Avance de la extracción de detalle"
                actual={datos.progreso.actual}
                total={datos.progreso.total}
                porcentaje={datos.progreso.porcentaje}
                mensaje={datos.progreso.mensaje || TEXTO_ESTADO[datos.estado]}
              />

              <dl className={layout.definiciones}>
                <div>
                  <dt className={layout.termino}>Identificador</dt>
                  <dd className={layout.descripcion}>{datos.job_id}</dd>
                </div>
                <div>
                  <dt className={layout.termino}>Tipo</dt>
                  <dd className={layout.descripcion}>{datos.tipo}</dd>
                </div>
                <div>
                  <dt className={layout.termino}>Creado</dt>
                  <dd className={layout.descripcion}>{formatearFechaHora(datos.creado_en)}</dd>
                </div>
                <div>
                  <dt className={layout.termino}>Actualizado</dt>
                  <dd className={layout.descripcion}>
                    {formatearFechaHora(datos.actualizado_en)}
                  </dd>
                </div>
              </dl>

              {datos.error ? (
                <ErrorState titulo="El trabajo terminó con error" texto={datos.error} />
              ) : null}

              {datos.resultado ? (
                <pre className={layout.preformateado}>
                  {JSON.stringify(datos.resultado, null, 2)}
                </pre>
              ) : null}

              {datos.estado === 'completado' ? (
                <p className={layout.textoSecundario}>
                  <Link to={`/periodos/${encodeURIComponent(periodo)}`}>
                    Ver los comprobantes con su detalle
                  </Link>
                </p>
              ) : null}
            </>
          ) : null}

          {job.isError ? (
            <ErrorState
              titulo="No se pudo consultar el estado del trabajo"
              texto={job.error instanceof ApiError ? job.error.message : 'Error inesperado.'}
            />
          ) : null}
        </Panel>
      </div>
    </>
  );
}

