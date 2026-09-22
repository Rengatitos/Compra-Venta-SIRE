import type { ReactNode } from 'react';

import estilos from './IconosNav.module.css';

/**
 * Iconos de la barra lateral, dibujados a mano como el resto del proyecto: no
 * hay paquete de iconos y meter uno por doce trazos no sale a cuenta. Cada uno
 * representa lo que hay al otro lado —el mosaico del resumen, el calendario de
 * los periodos, el ciclo de las corridas— para que la columna se lea de un
 * vistazo.
 *
 * Son decorativos: el nombre accesible de cada fila lo pone siempre su texto.
 */
function Lienzo({ children, chevron = false }: { children: ReactNode; chevron?: boolean }) {
  return (
    <svg
      className={chevron ? (estilos.chevron ?? '') : (estilos.icono ?? '')}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** Mosaico de paneles: el resumen. */
export function IconoPanel() {
  return (
    <Lienzo>
      <rect x="3.5" y="3.5" width="7" height="8.5" rx="1.75" />
      <rect x="13.5" y="3.5" width="7" height="5" rx="1.75" />
      <rect x="13.5" y="12" width="7" height="8.5" rx="1.75" />
      <rect x="3.5" y="15.5" width="7" height="5" rx="1.75" />
    </Lienzo>
  );
}

/** Calendario: un periodo es un mes. */
export function IconoPeriodos() {
  return (
    <Lienzo>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2.25" />
      <path d="M3.5 9.75h17M8.25 3.5v3M15.75 3.5v3" />
    </Lienzo>
  );
}

/** Flechas en ciclo: una corrida que se repite. */
export function IconoProcesos() {
  return (
    <Lienzo>
      <path d="M20.25 12a8.25 8.25 0 0 1-14.2 5.7" />
      <path d="M3.75 12a8.25 8.25 0 0 1 14.2-5.7" />
      <path d="M17.95 2.9v3.4h-3.4M6.05 21.1v-3.4h3.4" />
    </Lienzo>
  );
}

/** Libro abierto: el maestro de cuentas. */
export function IconoCuentas() {
  return (
    <Lienzo>
      <path d="M12 6.4S10.2 4.5 4.75 4.5v12.1C10.2 16.6 12 18.5 12 18.5s1.8-1.9 7.25-1.9V4.5C13.8 4.5 12 6.4 12 6.4Z" />
      <path d="M12 6.4v12.1" />
    </Lienzo>
  );
}

/** Deslizadores: los ajustes de la empresa. */
export function IconoAjustes() {
  return (
    <Lienzo>
      <path d="M3.75 7.5h10.5M18.75 7.5h1.5M3.75 16.5h5.5M13.75 16.5h6.5" />
      <circle cx="16.5" cy="7.5" r="2.25" />
      <circle cx="11.5" cy="16.5" r="2.25" />
    </Lienzo>
  );
}

/** Documento con renglones: los comprobantes del periodo. */
export function IconoComprobantes() {
  return (
    <Lienzo>
      <path d="M13.9 3.25H7.75A2.5 2.5 0 0 0 5.25 5.75v12.5a2.5 2.5 0 0 0 2.5 2.5h8.5a2.5 2.5 0 0 0 2.5-2.5V7.9Z" />
      <path d="M13.75 3.4v4.35h4.85" />
      <path d="M8.75 13h6.5M8.75 16.25h4.25" />
    </Lienzo>
  );
}

/** Escudo con visto: el cruce de la auditoría. */
export function IconoAuditoria() {
  return (
    <Lienzo>
      <path d="M12 3.25 4.75 6v6.1c0 4.35 3 7.45 7.25 8.65 4.25-1.2 7.25-4.3 7.25-8.65V6Z" />
      <path d="m9 11.9 2.3 2.3 4.2-4.4" />
    </Lienzo>
  );
}

/** Burbuja de chat con un recibo: lo que llega desde Apaclla Bot. */
export function IconoExternos() {
  return (
    <Lienzo>
      <path d="M5.25 4.25h13.5a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5H10l-4.25 3.5v-3.5h-.5a1.5 1.5 0 0 1-1.5-1.5v-9a1.5 1.5 0 0 1 1.5-1.5Z" />
      <path d="M8.5 8.75h7M8.5 12h4.5" />
    </Lienzo>
  );
}

/** Barras: el reporte del periodo. */
export function IconoReporte() {
  return (
    <Lienzo>
      <path d="M4.25 20h15.5" />
      <path d="M7.5 20v-5.75M12 20V8.25M16.5 20v-9" />
    </Lienzo>
  );
}

/** Punta a la derecha. Gira 90° con CSS al desplegar el grupo. */
export function IconoChevron() {
  return (
    <Lienzo chevron>
      <path d="M9.25 5.5 15.75 12l-6.5 6.5" />
    </Lienzo>
  );
}

/** Tres trazos: el menú de navegación en móvil. */
export function IconoMenu() {
  return (
    <Lienzo>
      <path d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
    </Lienzo>
  );
}

/** Aspa: cerrar el cajón. */
export function IconoCerrar() {
  return (
    <Lienzo>
      <path d="m6.25 6.25 11.5 11.5M17.75 6.25 6.25 17.75" />
    </Lienzo>
  );
}

/** Puerta con una flecha saliendo: cerrar sesión. */
export function IconoSalir() {
  return (
    <Lienzo>
      <path d="M14.25 4.75H7.75A2.25 2.25 0 0 0 5.5 7v10a2.25 2.25 0 0 0 2.25 2.25h6.5" />
      <path d="m16.25 15.5 3.5-3.5-3.5-3.5M19.5 12h-9" />
    </Lienzo>
  );
}
