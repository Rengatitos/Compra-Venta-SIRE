/**
 * Único punto del frontend que toca `fetch`. Todo lo demás pasa por aquí, así
 * que la cabecera Bearer, el formato de error de FastAPI, el manejo del 401 y la
 * descarga de binarios están resueltos en un solo sitio.
 */
import { limpiarSesion, obtenerToken } from './session';

/** En desarrollo `/api/v1` pasa por el proxy de Vite (ver vite.config.ts). */
const BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

export type Consulta = Record<string, string | number | boolean | null | undefined>;

/** Error de la API con el `detail` de FastAPI ya extraído. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, mensaje: string) {
    super(mensaje);
    this.name = 'ApiError';
    this.status = status;
  }

  /** Límites declarados con slowapi en el backend. */
  get esLimiteDeTasa(): boolean {
    return this.status === 429;
  }

  get esNoEncontrado(): boolean {
    return this.status === 404;
  }

  get esConflicto(): boolean {
    return this.status === 409;
  }

  get esNoImplementado(): boolean {
    return this.status === 501;
  }
}

/**
 * Se registra desde AuthProvider para no acoplar esta capa al router: cuando el
 * JWT caduca (caso normal, dura 2 h) hay que salir de la sesión y volver a login.
 */
let alExpirar: (() => void) | null = null;

export function registrarManejadorDeSesionExpirada(manejador: (() => void) | null): void {
  alExpirar = manejador;
}

function construirUrl(ruta: string, consulta?: Consulta): string {
  const url = `${BASE}${ruta}`;
  if (!consulta) return url;

  const params = new URLSearchParams();
  for (const [clave, valor] of Object.entries(consulta)) {
    if (valor === null || valor === undefined || valor === '') continue;
    params.append(clave, String(valor));
  }
  const cadena = params.toString();
  return cadena ? `${url}?${cadena}` : url;
}

function cabeceras(extra?: HeadersInit): Headers {
  const salida = new Headers(extra);
  const token = obtenerToken();
  if (token) salida.set('Authorization', `Bearer ${token}`);
  return salida;
}

const MENSAJES_POR_ESTADO: Record<number, string> = {
  401: 'La sesión expiró. Vuelve a iniciar sesión.',
  403: 'Esta cuenta no tiene acceso a ese recurso.',
  429: 'Demasiadas peticiones seguidas. Espera un minuto y vuelve a intentarlo.',
  500: 'El servidor tuvo un problema al procesar la petición.',
  502: 'SUNAT no respondió correctamente. Inténtalo de nuevo en unos minutos.',
  503: 'El servicio no está disponible en este momento.',
};

/** El `detail` de FastAPI es una cadena, o una lista de errores si es de validación. */
async function extraerDetalle(respuesta: Response): Promise<string> {
  try {
    const cuerpo: unknown = await respuesta.json();
    if (cuerpo && typeof cuerpo === 'object' && 'detail' in cuerpo) {
      const detalle: unknown = cuerpo.detail;
      if (typeof detalle === 'string' && detalle.trim()) return detalle;
      if (Array.isArray(detalle)) {
        const mensajes = detalle
          .map((item: unknown) => {
            if (item && typeof item === 'object' && 'msg' in item) {
              const msg: unknown = item.msg;
              return typeof msg === 'string' ? msg : null;
            }
            return null;
          })
          .filter((msg): msg is string => msg !== null);
        if (mensajes.length > 0) return mensajes.join('. ');
      }
    }
  } catch {
    // Respuesta sin JSON (por ejemplo un 502 del proxy): se usa el respaldo.
  }
  return MENSAJES_POR_ESTADO[respuesta.status] ?? `Error ${respuesta.status} en la petición.`;
}

async function ejecutar(url: string, init: RequestInit): Promise<Response> {
  let respuesta: Response;
  try {
    respuesta = await fetch(url, init);
  } catch {
    throw new ApiError(0, 'No se pudo contactar con el servidor. Revisa tu conexión.');
  }

  if (respuesta.ok) return respuesta;

  const mensaje = await extraerDetalle(respuesta);

  if (respuesta.status === 401) {
    limpiarSesion();
    alExpirar?.();
  }

  throw new ApiError(respuesta.status, mensaje);
}

interface OpcionesPeticion {
  metodo?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  cuerpo?: unknown;
  consulta?: Consulta;
  signal?: AbortSignal;
}

/** Petición JSON tipada. Usa `T = void` para respuestas sin cuerpo. */
export async function pedir<T>(ruta: string, opciones: OpcionesPeticion = {}): Promise<T> {
  const { metodo = 'GET', cuerpo, consulta, signal } = opciones;

  const cabeceraPeticion = cabeceras();
  if (cuerpo !== undefined) cabeceraPeticion.set('Content-Type', 'application/json');

  const respuesta = await ejecutar(construirUrl(ruta, consulta), {
    method: metodo,
    headers: cabeceraPeticion,
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    signal: signal ?? null,
  });

  if (respuesta.status === 204) return undefined as T;
  return (await respuesta.json()) as T;
}

/**
 * Multipart. No se fija `Content-Type` a mano: el navegador lo escribe con su
 * propio boundary, que es lo que espera FastAPI.
 */
export async function enviarFormulario<T>(ruta: string, datos: FormData): Promise<T> {
  const respuesta = await ejecutar(construirUrl(ruta), {
    method: 'POST',
    headers: cabeceras(),
    body: datos,
  });
  return (await respuesta.json()) as T;
}

const RE_NOMBRE_ARCHIVO = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i;

function nombreDesdeCabecera(respuesta: Response, porDefecto: string): string {
  const disposicion = respuesta.headers.get('Content-Disposition');
  const coincidencia = disposicion ? RE_NOMBRE_ARCHIVO.exec(disposicion) : null;
  const capturado = coincidencia?.[1];
  if (!capturado) return porDefecto;
  try {
    return decodeURIComponent(capturado.trim());
  } catch {
    return capturado.trim();
  }
}

/**
 * Descarga binaria para los endpoints `…/export`. No pasa por el parseo JSON y
 * respeta el `Content-Disposition` que ya envía el backend.
 */
export async function descargar(
  ruta: string,
  nombrePorDefecto: string,
  consulta?: Consulta,
): Promise<void> {
  const respuesta = await ejecutar(construirUrl(ruta, consulta), {
    method: 'GET',
    headers: cabeceras(),
  });

  const blob = await respuesta.blob();
  const url = URL.createObjectURL(blob);
  try {
    const enlace = document.createElement('a');
    enlace.href = url;
    enlace.download = nombreDesdeCabecera(respuesta, nombrePorDefecto);
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Los `serie_numero` pueden traer caracteres reservados: codificar siempre. */
export function segmento(valor: string): string {
  return encodeURIComponent(valor);
}
