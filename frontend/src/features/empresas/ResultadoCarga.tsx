import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';

import { descargarReporteCarga, obtenerCarga } from '@/api/empresas';
import { Badge, type TonoInsignia } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { type Columna, DataTable } from '@/components/ui/DataTable';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { ProgressBar } from '@/components/ui/Progress';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { CargaEmpresas, FilaCarga } from '@/types/api';
import type { EstadoFilaCarga } from '@/types/domain';

import estilos from './ResultadoCarga.module.css';

const INTERVALO_MS = 2000;

const ESTADOS: Record<EstadoFilaCarga, { tono: TonoInsignia; texto: string }> = {
  pendiente: { tono: 'info', texto: 'En proceso' },
  agregada: { tono: 'exito', texto: 'Agregada' },
  agregada_con_observaciones: { tono: 'aviso', texto: 'Agregada con observaciones' },
  no_agregada: { tono: 'error', texto: 'No agregada' },
};

interface Props {
  cargaId: string;
  /** Se llama una vez, cuando ya no queda ninguna fila en proceso. */
  onTerminada?: (carga: CargaEmpresas) => void;
  /** Acción extra junto a «Descargar reporte» (p. ej. entrar a la empresa). */
  accion?: ReactNode;
}

/**
 * Avance y reporte de una carga de empresas. Sondea el backend mientras quedan
 * filas por completar: cada una consulta SUNAT en la cola, así que el reporte
 * se va llenando fila a fila. Cerrar la página no lo detiene.
 */
export function ResultadoCarga({ cargaId, onTerminada, accion }: Props) {
  const { mostrar } = useToast();
  const avisada = useRef(false);

  const carga = useQuery({
    queryKey: ['carga-empresas', cargaId],
    queryFn: () => obtenerCarga(cargaId),
    refetchInterval: (consulta) =>
      consulta.state.data?.estado === 'completada' ? false : INTERVALO_MS,
  });

  const datos = carga.data;
  useEffect(() => {
    if (datos?.estado === 'completada' && !avisada.current) {
      avisada.current = true;
      onTerminada?.(datos);
    }
  }, [datos, onTerminada]);

  if (carga.isPending) return <Skeleton lineas={4} etiqueta="Cargando el resultado" />;
  if (carga.isError || !datos) {
    return (
      <ErrorState
        titulo="No se pudo leer la carga"
        texto={carga.error instanceof ApiError ? carga.error.message : 'Error inesperado.'}
      />
    );
  }

  const conteo = contar(datos.filas);
  const columnas: readonly Columna<FilaCarga>[] = [
    {
      clave: 'ruc',
      cabecera: 'RUC',
      monoespaciada: true,
      cabeceraDeFila: true,
      render: (f) => f.ruc || '—',
    },
    {
      clave: 'razon',
      cabecera: 'Razón social',
      anchoMinimo: '14rem',
      render: (f) => f.razon_social || '—',
    },
    {
      clave: 'usuario',
      cabecera: 'Usuario',
      monoespaciada: true,
      render: (f) => f.usuario || '—',
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (f) => {
        const estado = ESTADOS[f.estado] ?? { tono: 'neutro', texto: f.estado };
        return (
          <Badge tono={estado.tono} conPunto>
            {estado.texto}
          </Badge>
        );
      },
    },
    {
      clave: 'motivo',
      cabecera: 'Motivo',
      anchoMinimo: '18rem',
      render: (f) => f.motivos.join(' · ') || '—',
    },
  ];

  async function alDescargar() {
    try {
      await descargarReporteCarga(cargaId);
    } catch (fallo) {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo descargar el reporte',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    }
  }

  return (
    <div className={layout.pila}>
      {datos.estado === 'completada' ? (
        <p className={estilos.resumen} aria-live="polite">
          {conteo.agregada} agregadas · {conteo.agregada_con_observaciones} con observaciones ·{' '}
          {conteo.no_agregada} no agregadas
        </p>
      ) : (
        <ProgressBar
          etiqueta="Registro de empresas"
          actual={datos.progreso.actual}
          total={datos.progreso.total}
          porcentaje={
            datos.progreso.total ? (datos.progreso.actual / datos.progreso.total) * 100 : 0
          }
          mensaje={`${datos.progreso.mensaje}. Puedes cerrar esta página: el registro sigue en el servidor.`}
        />
      )}
      <DataTable
        leyenda="Resultado por empresa"
        columnas={columnas}
        filas={datos.filas}
        claveDeFila={(f) => String(f.fila)}
      />
      <div className={layout.filaFin}>
        {accion}
        <Button variante="secundario" onClick={() => void alDescargar()}>
          Descargar reporte
        </Button>
      </div>
    </div>
  );
}

function contar(filas: readonly FilaCarga[]): Record<EstadoFilaCarga, number> {
  const conteo: Record<EstadoFilaCarga, number> = {
    pendiente: 0,
    agregada: 0,
    agregada_con_observaciones: 0,
    no_agregada: 0,
  };
  for (const fila of filas) conteo[fila.estado] += 1;
  return conteo;
}
