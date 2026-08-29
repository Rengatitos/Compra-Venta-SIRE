/** Formateo para presentación. Funciones puras, sin dependencias de React. */

/** Nombres en minúscula: quien los muestre decide si van capitalizados. */
export const MESES = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
] as const;

const formateadorFecha = new Intl.DateTimeFormat('es-PE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  timeZone: 'UTC',
});

const formateadorEntero = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 0 });
const formateadorCantidad = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 3 });

const cacheMoneda = new Map<string, Intl.NumberFormat>();

function formateadorMoneda(moneda: string): Intl.NumberFormat {
  const clave = moneda || 'PEN';
  let formateador = cacheMoneda.get(clave);
  if (!formateador) {
    try {
      formateador = new Intl.NumberFormat('es-PE', {
        style: 'currency',
        currency: clave,
        minimumFractionDigits: 2,
      });
    } catch {
      // Código de moneda que SUNAT trajo con basura: se cae a decimal simple.
      formateador = new Intl.NumberFormat('es-PE', { minimumFractionDigits: 2 });
    }
    cacheMoneda.set(clave, formateador);
  }
  return formateador;
}

export function formatearMoneda(valor: number | null | undefined, moneda = 'PEN'): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return '—';
  return formateadorMoneda(moneda).format(valor);
}

/** Montos grandes en las métricas del dashboard: 1 250 000 → "S/ 1.25 M". */
export function formatearMontoCompacto(valor: number | null | undefined, moneda = 'PEN'): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return '—';
  const simbolo = moneda === 'PEN' ? 'S/' : moneda;
  const absoluto = Math.abs(valor);
  if (absoluto >= 1_000_000) return `${simbolo} ${(valor / 1_000_000).toFixed(2)} M`;
  if (absoluto >= 10_000) return `${simbolo} ${(valor / 1000).toFixed(1)} K`;
  return formatearMoneda(valor, moneda);
}

export function formatearEntero(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return '—';
  return formateadorEntero.format(valor);
}

/** Cantidades de los ítems: hasta 3 decimales y sin ceros de relleno. */
export function formatearCantidad(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return '—';
  return formateadorCantidad.format(valor);
}

/** `fecha_emision` llega como `YYYY-MM-DD` y puede ser null. */
export function formatearFecha(iso: string | null | undefined): string {
  if (!iso) return '—';
  const fecha = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(fecha.getTime())) return iso;
  return formateadorFecha.format(fecha);
}

/** Marcas de tiempo de los jobs, que sí traen hora. */
export function formatearFechaHora(iso: string | null | undefined): string {
  if (!iso) return '—';
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return new Intl.DateTimeFormat('es-PE', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(fecha);
}

/** `202606` → `Junio 2026`. Devuelve la entrada tal cual si no es YYYYMM. */
export function formatearPeriodo(periodo: string): string {
  if (!/^\d{6}$/.test(periodo)) return periodo;
  const mes = MESES[Number(periodo.slice(4, 6)) - 1];
  if (!mes) return periodo;
  return `${mes.charAt(0).toUpperCase()}${mes.slice(1)} ${periodo.slice(0, 4)}`;
}

/** Periodo del mes anterior, que es el que un contador suele estar cerrando. */
export function periodoPorDefecto(hoy = new Date()): string {
  const fecha = new Date(Date.UTC(hoy.getUTCFullYear(), hoy.getUTCMonth() - 1, 1));
  const mes = String(fecha.getUTCMonth() + 1).padStart(2, '0');
  return `${fecha.getUTCFullYear()}${mes}`;
}

/** `202606` → `{ anio: '2026', mes: '06' }`. Para poblar los selectores. */
export function partirPeriodo(periodo: string): { anio: string; mes: string } {
  return { anio: periodo.slice(0, 4), mes: periodo.slice(4, 6) };
}

/** Inversa de `partirPeriodo`. El mes se rellena a dos dígitos. */
export function componerPeriodo(anio: string, mes: string): string {
  return `${anio}${mes.padStart(2, '0')}`;
}

/**
 * Años que ofrece el selector: el actual y los cinco anteriores, que es el
 * horizonte con el que trabaja un contador. Todos caen dentro de lo que admite
 * `PERIODO_RE` (`20xx`).
 */
export function aniosDisponibles(hoy = new Date()): string[] {
  const actual = hoy.getUTCFullYear();
  return Array.from({ length: 6 }, (_, indice) => String(actual - indice));
}

export function formatearPorcentaje(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return '—';
  return `${Math.round(valor)} %`;
}
