/**
 * Sesión del navegador. Se usa `sessionStorage` y no `localStorage` a propósito:
 * el JWT del backend vive `JWT_EXPIRE_HOURS` (2 h por defecto), así que
 * persistirlo entre sesiones del navegador solo dejaría credenciales muertas en
 * disco. Ni el token ni el RUC viajan nunca por query string.
 */

const CLAVE = 'sire.sesion';

export interface Sesion {
  token: string;
  ruc: string;
}

type Oyente = (sesion: Sesion | null) => void;

const oyentes = new Set<Oyente>();

function leerAlmacen(): Sesion | null {
  try {
    const crudo = sessionStorage.getItem(CLAVE);
    if (!crudo) return null;
    const dato = JSON.parse(crudo) as Partial<Sesion>;
    if (typeof dato.token !== 'string' || typeof dato.ruc !== 'string') return null;
    return { token: dato.token, ruc: dato.ruc };
  } catch {
    // Modo privado, almacenamiento bloqueado o JSON corrupto: sin sesión.
    return null;
  }
}

let sesion: Sesion | null = leerAlmacen();

export function obtenerSesion(): Sesion | null {
  return sesion;
}

export function obtenerToken(): string | null {
  return sesion?.token ?? null;
}

function emitir(): void {
  for (const oyente of oyentes) oyente(sesion);
}

export function guardarSesion(nueva: Sesion): void {
  sesion = nueva;
  try {
    sessionStorage.setItem(CLAVE, JSON.stringify(nueva));
  } catch {
    // Sin almacenamiento la sesión sigue viva en memoria hasta recargar.
  }
  emitir();
}

export function limpiarSesion(): void {
  sesion = null;
  try {
    sessionStorage.removeItem(CLAVE);
  } catch {
    /* nada que limpiar */
  }
  emitir();
}

export function suscribirSesion(oyente: Oyente): () => void {
  oyentes.add(oyente);
  return () => {
    oyentes.delete(oyente);
  };
}
