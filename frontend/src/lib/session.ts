/**
 * Sesión del navegador. Se usa `sessionStorage` y no `localStorage` a propósito:
 * el JWT del backend vive `JWT_EXPIRE_HOURS` (2 h por defecto), así que
 * persistirlo entre sesiones del navegador solo dejaría credenciales muertas en
 * disco. Ni el token ni el RUC viajan nunca por query string.
 *
 * El token identifica a una **persona** (el correo con el que entró por Google),
 * no a una empresa. La empresa activa se guarda aquí mismo, dentro del objeto de
 * sesión, y eso la ata al correo por construcción: si en la misma pestaña entra
 * otra persona, no hereda la empresa que dejó elegida la anterior.
 */

const CLAVE = 'sire.sesion';

export interface Sesion {
  token: string;
  correo: string;
  nombre?: string;
  /** RUC de la empresa activa. Nulo hasta que se elige una. */
  ruc: string | null;
}

type Oyente = (sesion: Sesion | null) => void;

const oyentes = new Set<Oyente>();

function leerAlmacen(): Sesion | null {
  try {
    const crudo = sessionStorage.getItem(CLAVE);
    if (!crudo) return null;
    const dato = JSON.parse(crudo) as Partial<Sesion>;
    // Una sesión de la forma anterior (`{token, ruc}`, sin correo) no valida y
    // se descarta: su JWT identificaba a una empresa y el backend ya no lo
    // acepta, así que lo correcto es mandar a la persona a iniciar sesión.
    if (typeof dato.token !== 'string' || typeof dato.correo !== 'string') return null;
    return {
      token: dato.token,
      correo: dato.correo,
      nombre: typeof dato.nombre === 'string' ? dato.nombre : undefined,
      ruc: typeof dato.ruc === 'string' ? dato.ruc : null,
    };
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

function escribir(nueva: Sesion | null): void {
  sesion = nueva;
  try {
    if (nueva) sessionStorage.setItem(CLAVE, JSON.stringify(nueva));
    else sessionStorage.removeItem(CLAVE);
  } catch {
    // Sin almacenamiento la sesión sigue viva en memoria hasta recargar.
  }
  emitir();
}

export function guardarSesion(nueva: Sesion): void {
  escribir(nueva);
}

/**
 * Cambia solo la empresa activa. El resto de la sesión no se toca: elegir otra
 * cuenta no es volver a autenticarse, que es justo lo que esta pantalla viene a
 * evitar.
 */
export function guardarEmpresaActiva(ruc: string | null): void {
  if (!sesion) return;
  escribir({ ...sesion, ruc });
}

export function limpiarSesion(): void {
  escribir(null);
}

export function suscribirSesion(oyente: Oyente): () => void {
  oyentes.add(oyente);
  return () => {
    oyentes.delete(oyente);
  };
}
