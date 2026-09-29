import type { ComponentType } from 'react';

import {
  IconoAccesos,
  IconoAjustes,
  IconoAuditoria,
  IconoClasificaciones,
  IconoComprobantes,
  IconoCorreos,
  IconoCuentas,
  IconoEmpresas,
  IconoExternos,
  IconoHistorial,
  IconoMasivo,
  IconoPanel,
  IconoPeriodos,
  IconoProcesos,
  IconoReporte,
  IconoSolicitudes,
} from './IconosNav';

export interface SubEntrada {
  a: string;
  texto: string;
  icono: ComponentType;
  /** `end` para que el primer hijo no quede activo en `/auditoria` ni `/reporte`. */
  exacto?: boolean;
}

export interface Entrada {
  a: string;
  texto: string;
  icono: ComponentType;
  exacto?: boolean;
  /**
   * Con hijos la fila se parte en dos: el chevron es un botón de despliegue y el
   * resto sigue siendo el enlace a la sección. Un botón dentro de un enlace no
   * es HTML válido, y una fila que solo fuera botón dejaría `/periodos` sin
   * forma de alcanzarse desde la navegación.
   */
  hijos?: readonly SubEntrada[];
}

/**
 * El segundo nivel de «Periodos» es el contexto del periodo que se está
 * mirando, no una lista fija: existe solo dentro de `/periodos/:periodo`. Sin
 * periodo activo el grupo es un enlace normal al listado, sin chevron.
 */
export function subEntradasDePeriodo(periodo: string): readonly SubEntrada[] {
  const base = `/periodos/${encodeURIComponent(periodo)}`;
  return [
    { a: base, texto: 'Comprobantes', icono: IconoComprobantes, exacto: true },
    { a: `${base}/auditoria`, texto: 'Auditoría', icono: IconoAuditoria },
    { a: `${base}/reporte`, texto: 'Reporte', icono: IconoReporte },
  ];
}

/** Árbol de navegación del render actual. Puro: se prueba sin montar nada. */
export function construirNavegacion(periodo: string | null): readonly Entrada[] {
  return [
    { a: '/dashboard', texto: 'Dashboard', icono: IconoPanel },
    { a: '/clasificaciones', texto: 'Clasificaciones', icono: IconoClasificaciones },
    {
      a: '/periodos',
      texto: 'Periodos',
      icono: IconoPeriodos,
      // `exacto` siempre: si no, `/periodos` y el hijo activo pondrían dos
      // `aria-current="page"` en la misma lista. Que la sección esté abierta lo
      // dice una clase propia, no `aria-current`.
      exacto: true,
      hijos: periodo ? subEntradasDePeriodo(periodo) : undefined,
    },
    { a: '/externos', texto: 'Externos', icono: IconoExternos },
    { a: '/procesos', texto: 'Procesos', icono: IconoProcesos },
    { a: '/plan-cuentas', texto: 'Maestro de cuentas', icono: IconoCuentas },
    { a: '/ajustes', texto: 'Ajustes', icono: IconoAjustes },
  ];
}

/**
 * Secciones del panel de todas las empresas, que vive en la raíz. «Empresas» es
 * exacta: sin eso quedaría activa en todas las demás, que cuelgan de `/`.
 */
export function construirNavegacionGeneral(): readonly Entrada[] {
  return [
    { a: '/', texto: 'Empresas', icono: IconoEmpresas, exacto: true },
    { a: '/procesamiento', texto: 'Procesamiento masivo', icono: IconoMasivo },
    { a: '/solicitudes', texto: 'Solicitudes', icono: IconoSolicitudes },
    { a: '/historial', texto: 'Historial', icono: IconoHistorial },
    { a: '/correos', texto: 'Correos', icono: IconoCorreos },
    // Antes solo se llegaba desde los ajustes de cada empresa, aunque no
    // dependen de ninguna.
    { a: '/accesos', texto: 'Accesos', icono: IconoAccesos },
  ];
}
