import { useQuery } from '@tanstack/react-query';

import { listarCargas } from '@/api/empresas';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { formatearFechaHora } from '@/lib/format';
import { ApiError } from '@/lib/http';

import { describirCarga } from './cargas';
import estilos from './IngresosAnteriores.module.css';

const INTERVALO_MS = 3000;

interface Props {
  onAbrir: (cargaId: string) => void;
}

/**
 * Los registros de empresas ya hechos, del más reciente al más antiguo. El
 * reporte vive en el servidor, así que salir de la pantalla no lo pierde:
 * desde aquí se vuelve a él, y los que siguen en curso muestran su avance.
 */
export function IngresosAnteriores({ onAbrir }: Props) {
  const cargas = useQuery({
    queryKey: ['cargas-empresas'],
    queryFn: listarCargas,
    // Mientras alguno siga en proceso, su avance se refresca solo.
    refetchInterval: (consulta) =>
      consulta.state.data?.some((c) => c.estado !== 'completada') ? INTERVALO_MS : false,
  });

  if (cargas.isPending) return <Skeleton lineas={4} etiqueta="Cargando los ingresos anteriores" />;
  if (cargas.isError) {
    return (
      <ErrorState
        titulo="No se pudieron cargar los ingresos anteriores"
        texto={cargas.error instanceof ApiError ? cargas.error.message : 'Error inesperado.'}
        accion={
          <Button pequeno onClick={() => void cargas.refetch()}>
            Reintentar
          </Button>
        }
      />
    );
  }
  if (cargas.data.length === 0) {
    return (
      <EmptyState
        titulo="Todavía no hay ingresos"
        texto="Cuando registres empresas, aquí quedará cada ingreso con su reporte."
      />
    );
  }

  return (
    <ul className={estilos.lista} aria-label="Ingresos anteriores">
      {cargas.data.map((carga) => {
        const terminada = carga.estado === 'completada';
        const { actual, total } = carga.progreso;
        return (
          <li key={carga.id} className={estilos.fila}>
            <div className={estilos.datos}>
              <span className={estilos.fecha}>{formatearFechaHora(carga.creado_en)}</span>
              <span className={estilos.detalle}>
                {describirCarga(carga)} · {total} {total === 1 ? 'empresa' : 'empresas'} · por{' '}
                {carga.registrado_por}
              </span>
            </div>
            <div className={estilos.estado}>
              {terminada ? (
                <Badge tono="exito" conPunto>
                  Terminado
                </Badge>
              ) : (
                <>
                  <Badge tono="info" conPunto>
                    En proceso {actual}/{total}
                  </Badge>
                  <progress
                    className={estilos.barra}
                    value={actual}
                    max={total || 1}
                    aria-label={`Avance del ingreso del ${formatearFechaHora(carga.creado_en)}`}
                  />
                </>
              )}
            </div>
            <Button
              pequeno
              variante={terminada ? 'secundario' : 'primario'}
              onClick={() => onAbrir(carga.id)}
              aria-label={`${terminada ? 'Ver el reporte' : 'Ver el progreso'} del ingreso del ${formatearFechaHora(carga.creado_en)}`}
            >
              {terminada ? 'Ver reporte' : 'Ver progreso'}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}
