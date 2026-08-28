/**
 * Tema visual. El predeterminado es el claro; el oscuro se activa poniendo
 * `data-theme="dark"` en el elemento raíz, que es lo que leen los tokens
 * (ver src/styles/tokens.css).
 *
 * Los valores son `light` / `dark` a propósito, no sus nombres en español: son
 * los mismos que el atributo del DOM, la propiedad CSS `color-scheme` y lo que
 * lee el script en línea de index.html, así que hay un solo vocabulario.
 *
 * La preferencia se guarda en `localStorage`, no en `sessionStorage`: a
 * diferencia del token de sesión, es una comodidad del dispositivo que conviene
 * recordar entre visitas y no contiene nada sensible.
 *
 * No se sigue `prefers-color-scheme`: el requisito es arrancar en claro. Solo
 * se recuerda la elección explícita del usuario.
 */

export type Tema = 'light' | 'dark';

export const TEMA_POR_DEFECTO: Tema = 'light';

/** Compartida con el script en línea de index.html. */
const CLAVE = 'sire.tema';

type Oyente = (tema: Tema) => void;

const oyentes = new Set<Oyente>();

function leerAlmacen(): Tema | null {
  try {
    const valor = localStorage.getItem(CLAVE);
    return valor === 'dark' || valor === 'light' ? valor : null;
  } catch {
    // Modo privado o almacenamiento bloqueado: se usa el predeterminado.
    return null;
  }
}

/**
 * Cambiar el atributo basta: los tokens de color se sustituyen de golpe y
 * ninguna propiedad de color está en transición (ver la nota en
 * src/styles/global.css), así que no queda nada a medio animar.
 */
function aplicarAlDocumento(tema: Tema): void {
  document.documentElement.dataset.theme = tema;
}

let tema: Tema = leerAlmacen() ?? TEMA_POR_DEFECTO;

/**
 * El script en línea de index.html ya deja el atributo puesto antes del primer
 * pintado; esto solo garantiza que el DOM y el estado coincidan si ese script
 * no llegó a ejecutarse (por ejemplo en los tests).
 */
aplicarAlDocumento(tema);

export function obtenerTema(): Tema {
  return tema;
}

export function establecerTema(nuevo: Tema): void {
  tema = nuevo;
  aplicarAlDocumento(nuevo);
  try {
    localStorage.setItem(CLAVE, nuevo);
  } catch {
    // Sin almacenamiento el tema vive hasta que se recargue la página.
  }
  for (const oyente of oyentes) oyente(nuevo);
}

export function alternarTema(): Tema {
  const siguiente: Tema = tema === 'dark' ? 'light' : 'dark';
  establecerTema(siguiente);
  return siguiente;
}

export function suscribirTema(oyente: Oyente): () => void {
  oyentes.add(oyente);
  return () => {
    oyentes.delete(oyente);
  };
}
