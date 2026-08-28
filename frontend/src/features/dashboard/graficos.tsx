import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';

import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { formatearEntero, formatearMontoCompacto } from '@/lib/format';
import type { ClasificacionIA, ComprobantesPorDia, ContraparteTop } from '@/types/api';

import estilos from './Dashboard.module.css';
import { GraficoAccesible } from './GraficoAccesible';

/**
 * Los colores vienen de los tokens: `var(--chart-n)` se resuelve en el SVG igual
 * que en cualquier otro elemento, así que no hay paleta duplicada en JS.
 */
const SERIES = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)'];

const EJE = {
  stroke: 'var(--chart-grid)',
  tick: { fill: 'var(--color-text-secondary)', fontSize: 11 },
};

export function SerieDiaria({ datos }: { datos: readonly ComprobantesPorDia[] }) {
  const reducido = usePrefersReducedMotion();

  return (
    <GraficoAccesible
      leyenda="Comprobantes emitidos por día del mes"
      encabezadoNombre="Día"
      encabezadoValor="Comprobantes"
      filas={datos.map((punto) => ({
        nombre: punto.name,
        valor: formatearEntero(punto.qty),
      }))}
    >
      <div className={estilos.grafico}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={[...datos]} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="degradadoSerie" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
                <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="name"
              stroke={EJE.stroke}
              tick={EJE.tick}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis stroke={EJE.stroke} tick={EJE.tick} tickLine={false} width={32} />
            <Area
              type="monotone"
              dataKey="qty"
              stroke="var(--chart-1)"
              strokeWidth={2}
              fill="url(#degradadoSerie)"
              isAnimationActive={!reducido}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </GraficoAccesible>
  );
}

export function TopContrapartes({ datos }: { datos: readonly ContraparteTop[] }) {
  const reducido = usePrefersReducedMotion();

  return (
    <GraficoAccesible
      leyenda="Contrapartes con mayor monto acumulado en el periodo"
      encabezadoNombre="Contraparte"
      encabezadoValor="Monto"
      filas={datos.map((fila) => ({
        nombre: fila.name,
        valor: formatearMontoCompacto(fila.total),
      }))}
    >
      <div className={estilos.graficoAlto}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={[...datos]}
            layout="vertical"
            margin={{ top: 8, right: 8, bottom: 0, left: 8 }}
          >
            <XAxis type="number" stroke={EJE.stroke} tick={EJE.tick} tickLine={false} />
            <YAxis
              type="category"
              dataKey="name"
              stroke={EJE.stroke}
              tick={EJE.tick}
              tickLine={false}
              width={120}
            />
            <Bar
              dataKey="total"
              fill="var(--chart-2)"
              radius={[0, 6, 6, 0]}
              isAnimationActive={!reducido}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </GraficoAccesible>
  );
}

export function DistribucionIA({ datos }: { datos: readonly ClasificacionIA[] }) {
  const reducido = usePrefersReducedMotion();

  return (
    <GraficoAccesible
      leyenda="Distribución de comprobantes por clasificación de la IA"
      encabezadoNombre="Clasificación"
      encabezadoValor="Comprobantes"
      filas={datos.map((fila) => ({
        nombre: String(fila.name),
        valor: formatearEntero(fila.value),
      }))}
    >
      <div className={estilos.grafico}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={[...datos]}
              dataKey="value"
              nameKey="name"
              innerRadius="58%"
              outerRadius="82%"
              paddingAngle={2}
              stroke="var(--color-bg)"
              isAnimationActive={!reducido}
            >
              {datos.map((fila, indice) => (
                <Cell key={String(fila.name)} fill={SERIES[indice % SERIES.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
    </GraficoAccesible>
  );
}
