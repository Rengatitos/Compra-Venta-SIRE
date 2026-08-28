import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link } from 'react-router';

import { obtenerDashboard, obtenerPeriodosConDatos } from '@/api/analytics';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, MetricTile, Skeleton } from '@/components/ui/Feedback';
import { SelectField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { presentarEstadoComprobante } from '@/features/comprobantes/estadoComprobante';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import {
  formatearEntero,
  formatearFecha,
  formatearMoneda,
  formatearMontoCompacto,
  formatearPeriodo,
  formatearPorcentaje,
  periodoPorDefecto,
} from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ComprobanteResponse } from '@/types/api';

import estilos from './Dashboard.module.css';
import { DistribucionIA, SerieDiaria, TopContrapartes } from './graficos';

export function DashboardPage() {
  useDocumentTitle('Dashboard');

  const ruc = useRuc();
  const rucs = useMemo(() => [ruc], [ruc]);

  const [periodo, setPeriodo] = useState(() => periodoPorDefecto());

  // Los endpoints de analytics filtran por `rucs`; sin ese parámetro no
  // devuelven nada, así que siempre se envía el RUC de la sesión.
  const periodos = useQuery({
    queryKey: ['analytics-periodos', ruc],
    queryFn: () => obtenerPeriodosConDatos(rucs),
    staleTime: 60_000,
  });

  const dashboard = useQuery({
    queryKey: ['dashboard', ruc, periodo],
    queryFn: () => obtenerDashboard(rucs, periodo, 'compras'),
  });

  const opcionesPeriodo = useMemo(() => {
    const disponibles = periodos.data ?? [];
    const conjunto = [...new Set([...disponibles, periodo])].sort().reverse();
    return conjunto.map((codigo) => ({
      valor: codigo,
      texto: `${formatearPeriodo(codigo)} (${codigo})`,
    }));
  }, [periodos.data, periodo]);

  const datos = dashboard.data;
  const resumen = datos?.summary;
  const totalAnalisis = resumen ? resumen.procesadas + resumen.pendientes : 0;
  const cobertura = totalAnalisis > 0 ? ((resumen?.procesadas ?? 0) / totalAnalisis) * 100 : 0;

  const columnas: readonly Columna<ComprobanteResponse>[] = [
    {
      clave: 'serie_numero',
      cabecera: 'Comprobante',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => (
        <Link
          to={`/periodos/${encodeURIComponent(periodo)}/comprobantes/${encodeURIComponent(
            fila.serie_numero,
          )}`}
        >
          {fila.serie_numero}
        </Link>
      ),
    },
    {
      clave: 'fecha_emision',
      cabecera: 'Emisión',
      monoespaciada: true,
      render: (fila) => formatearFecha(fila.fecha_emision),
    },
    {
      clave: 'razon_social',
      cabecera: 'Contraparte',
      render: (fila) => fila.razon_social || '—',
    },
    {
      clave: 'total',
      cabecera: 'Total',
      numerica: true,
      render: (fila) => formatearMoneda(fila.total, fila.moneda),
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (fila) => {
        const estado = presentarEstadoComprobante(fila.estado_procesamiento);
        return (
          <Badge tono={estado.tono} conPunto>
            {estado.texto}
          </Badge>
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        titulo="Panel del periodo"
        descripcion="Totales, ritmo diario, concentración por proveedor y avance de la clasificación con IA."
        acciones={
          <div className={estilos.selector}>
            <SelectField
              etiqueta="Periodo"
              value={periodo}
              onChange={(evento) => setPeriodo(evento.target.value)}
              opciones={opcionesPeriodo}
              mono
            />
          </div>
        }
      />

      {dashboard.isError ? (
        <ErrorState
          titulo="No se pudo cargar la analítica"
          texto={
            dashboard.error instanceof ApiError ? dashboard.error.message : 'Error inesperado.'
          }
          accion={
            <Button pequeno onClick={() => void dashboard.refetch()}>
              Reintentar
            </Button>
          }
        />
      ) : null}

      {dashboard.isPending ? <Skeleton lineas={5} etiqueta="Cargando el panel" /> : null}

      {datos && resumen ? (
        <div className={layout.pilaAmplia}>
          <div className={layout.rejillaMetricas}>
            <MetricTile
              etiqueta="Comprobantes"
              valor={formatearEntero(resumen.total_comprobantes)}
              nota={`Periodo ${formatearPeriodo(periodo)}`}
            />
            <MetricTile
              etiqueta="Monto total"
              valor={formatearMontoCompacto(resumen.total_monto)}
              nota="Suma del importe total"
            />
            <MetricTile
              etiqueta="IGV acumulado"
              valor={formatearMontoCompacto(resumen.total_igv)}
              nota="Crédito fiscal potencial"
            />
            <MetricTile
              etiqueta="Clasificados"
              valor={formatearPorcentaje(cobertura)}
              nota={`${formatearEntero(resumen.procesadas)} de ${formatearEntero(
                totalAnalisis,
              )} analizados`}
            />
          </div>

          {resumen.total_comprobantes === 0 ? (
            <EmptyState
              titulo={`El periodo ${formatearPeriodo(periodo)} no tiene datos`}
              texto="Crea el periodo y sincroniza su propuesta de compras para que aparezca aquí."
              accion={<Link to="/periodos">Ir a periodos</Link>}
            />
          ) : (
            <>
              <div className={layout.bento}>
                <div className={`${layout.bentoAncho ?? ''} ${estilos.entrada ?? ''}`}>
                  <Panel
                    titulo="Ritmo diario"
                    descripcion="Conteo agrupado por día de emisión dentro del periodo."
                    interactivo
                  >
                    <SerieDiaria datos={datos.comprobantes_por_dia} />
                  </Panel>
                </div>

                <div className={estilos.entrada} style={{ ['--indice' as string]: 1 }}>
                  <Panel
                    titulo="Clasificación de la IA"
                    descripcion="Solo cuenta los comprobantes que ya pasaron por el análisis."
                    interactivo
                  >
                    {datos.ai_classification.length > 0 ? (
                      <DistribucionIA datos={datos.ai_classification} />
                    ) : (
                      <EmptyState
                        titulo="Nada analizado todavía"
                        texto="Lanza el análisis con IA para ver la distribución contable."
                        accion={
                          <Link to={`/periodos/${encodeURIComponent(periodo)}/analisis`}>
                            Analizar el periodo
                          </Link>
                        }
                      />
                    )}
                  </Panel>
                </div>

                <div className={estilos.entrada} style={{ ['--indice' as string]: 2 }}>
                  <Panel
                    titulo="Principales contrapartes"
                    descripcion="Proveedores con mayor monto acumulado en el periodo."
                    interactivo
                  >
                    {datos.top_contrapartes.length > 0 ? (
                      <TopContrapartes datos={datos.top_contrapartes} />
                    ) : (
                      <EmptyState titulo="Sin contrapartes con monto acumulado" />
                    )}
                  </Panel>
                </div>
              </div>

              <Panel
                titulo="Últimos comprobantes"
                acciones={
                  <Link to={`/periodos/${encodeURIComponent(periodo)}`}>Ver el listado completo</Link>
                }
              >
                <DataTable
                  leyenda={`Comprobantes más recientes del periodo ${formatearPeriodo(periodo)}`}
                  leyendaOculta
                  columnas={columnas}
                  filas={datos.comprobantes.slice(0, 10)}
                  claveDeFila={(fila) => fila.serie_numero}
                  vacio={<EmptyState titulo="Sin comprobantes en el periodo" />}
                />
              </Panel>
            </>
          )}
        </div>
      ) : null}
    </>
  );
}
