/** Formateo para presentación. Funciones puras, sin dependencias de React. */

const MESES = [
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

export function formatearPorcentaje(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return '—';
  return `${Math.round(valor)} %`;
}

/** RUC de 11 dígitos agrupado para lectura: 20608997106 → 20 608997106. */
export function formatearRuc(ruc: string): string {
  return /^\d{11}$/.test(ruc) ? `${ruc.slice(0, 2)} ${ruc.slice(2)}` : ruc;
}
