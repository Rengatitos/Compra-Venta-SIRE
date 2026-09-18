import type { ReactNode } from 'react';

import estilos from './IconosExportacion.module.css';

/**
 * Iconos de las descargas de la cabecera de comprobantes. Cada uno dibuja el
 * formato que se descarga —hoja de cálculo, página, carpeta comprimida,
 * reporte con su adjunto— para que los cuatro botones se distingan de un
 * vistazo: una flecha de descarga repetida cuatro veces no diría cuál es cuál.
 *
 * Son decorativos: el nombre accesible del botón lo pone su texto.
 */
function Lienzo({ children }: { children: ReactNode }) {
  return (
    <svg
      className={estilos.icono}
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

/** Hoja de cálculo: rejilla de filas y columnas. */
export function IconoHojaCalculo() {
  return (
    <Lienzo>
      <rect x="3.25" y="4.5" width="17.5" height="15" rx="2.25" />
      <path d="M3.25 9.25h17.5M9.5 9.25v10.25M3.25 14.5h17.5" />
    </Lienzo>
  );
}

/** Página con la esquina doblada y renglones: el listado impreso. */
export function IconoListado() {
  return (
    <Lienzo>
      <path d="M13.9 3.25H7.75A2.5 2.5 0 0 0 5.25 5.75v12.5a2.5 2.5 0 0 0 2.5 2.5h8.5a2.5 2.5 0 0 0 2.5-2.5V7.9Z" />
      <path d="M13.75 3.4v4.35h4.85" />
      <path d="M8.75 13h6.5M8.75 16.25h4.25" />
    </Lienzo>
  );
}

/** Carpeta con cremallera: el ZIP. */
export function IconoZip() {
  return (
    <Lienzo>
      <path d="M3.5 7.5A2.25 2.25 0 0 1 5.75 5.25h3.1l1.9 2.35h7.5a2.25 2.25 0 0 1 2.25 2.25v8.15a2.25 2.25 0 0 1-2.25 2.25H5.75A2.25 2.25 0 0 1 3.5 18Z" />
      <path d="M12.3 9.9v1.4M13.7 11.3v1.4M12.3 12.7v1.4" />
      <rect x="11.5" y="14.5" width="3" height="3.4" rx="1" />
    </Lienzo>
  );
}

/** Reporte con gráfico y un documento detrás: el reporte y su asociado. */
export function IconoReporteAsociado() {
  return (
    <Lienzo>
      <path d="M16.25 6.25V5.5A2.25 2.25 0 0 0 14 3.25H6.75A2.25 2.25 0 0 0 4.5 5.5v9.25" />
      <rect x="8.25" y="6.75" width="11.25" height="14" rx="2.25" />
      <path d="M11.4 17.6v-2.6M13.9 17.6v-5.1M16.4 17.6v-3.6" />
    </Lienzo>
  );
}
