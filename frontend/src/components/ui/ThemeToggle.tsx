import { useSyncExternalStore } from 'react';

import { alternarTema, obtenerTema, suscribirTema, TEMA_POR_DEFECTO } from '@/lib/theme';

import estilos from './ThemeToggle.module.css';

/** Luna: la acción disponible cuando se está en claro. */
function IconoLuna() {
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
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
    </svg>
  );
}

/** Sol: la acción disponible cuando se está en oscuro. */
function IconoSol() {
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
      <circle cx="12" cy="12" r="4.25" />
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4" />
    </svg>
  );
}

/**
 * Cambia entre el tema claro y el oscuro. El icono muestra el tema al que se va
 * a cambiar, y el nombre accesible lo dice con palabras: un icono solo no basta
 * para un lector de pantalla.
 */
export function ThemeToggle() {
  const tema = useSyncExternalStore(suscribirTema, obtenerTema, () => TEMA_POR_DEFECTO);
  const esOscuro = tema === 'dark';
  const etiqueta = esOscuro ? 'Activar el modo claro' : 'Activar el modo oscuro';

  return (
    <button
      type="button"
      className={estilos.boton}
      onClick={() => alternarTema()}
      aria-label={etiqueta}
      title={etiqueta}
    >
      {esOscuro ? <IconoSol /> : <IconoLuna />}
    </button>
  );
}
