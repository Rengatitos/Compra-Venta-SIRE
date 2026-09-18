/**
 * Único punto del frontend que toca Google Identity Services, con el mismo
 * criterio que `http.ts` con `fetch`: encapsularlo es lo que permite simularlo
 * entero en los tests sin que jsdom intente salir a la red.
 *
 * Se carga el script oficial a mano en lugar de instalar `@react-oauth/google`,
 * que es un envoltorio del mismo script: no evita el iframe, ni el `client_id`,
 * ni registrar el origen en Google Cloud, y su `useGoogleLogin` usa el flujo de
 * *code*, que no es el que emplea este proyecto.
 */
import type { Tema } from './theme';

const URL_SCRIPT = 'https://accounts.google.com/gsi/client';

/**
 * No es un secreto y no pasa nada porque viaje en el bundle: lo que protege el
 * acceso son los «Orígenes de JavaScript autorizados» del cliente OAuth en
 * Google Cloud, más la lista de correos del backend.
 */
export const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? '';

/** Sin client id no hay nada que pintar; conviene decirlo antes de intentarlo. */
export function hayClientId(): boolean {
  return CLIENT_ID.trim() !== '';
}

export class ErrorGoogleIdentity extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = 'ErrorGoogleIdentity';
  }
}

/** Techo de espera del script. Sin él, un bloqueador dejaría la pantalla colgada. */
const ESPERA_MS = 8000;

let carga: Promise<void> | null = null;

/**
 * Inyecta el script de Google una sola vez. La promesa se guarda a nivel de
 * módulo porque en StrictMode el efecto que la llama se monta dos veces y no
 * puede acabar con dos `<script>` en el documento.
 */
export function cargarGoogleIdentity(): Promise<void> {
  if (carga) return carga;

  carga = new Promise<void>((resolver, rechazar) => {
    if (window.google?.accounts.id) {
      resolver();
      return;
    }

    const temporizador = window.setTimeout(() => {
      carga = null;
      rechazar(new ErrorGoogleIdentity('Google tardó demasiado en responder.'));
    }, ESPERA_MS);

    const script = document.createElement('script');
    script.src = URL_SCRIPT;
    script.async = true;
    script.defer = true;
    script.addEventListener('load', () => {
      window.clearTimeout(temporizador);
      if (window.google?.accounts.id) resolver();
      else {
        carga = null;
        rechazar(new ErrorGoogleIdentity('El script de Google se cargó incompleto.'));
      }
    });
    script.addEventListener('error', () => {
      window.clearTimeout(temporizador);
      carga = null;
      rechazar(new ErrorGoogleIdentity('No se pudo cargar el acceso con Google.'));
    });

    document.head.append(script);
  });

  return carga;
}

function accounts(): GoogleAccountsId {
  const api = window.google?.accounts.id;
  if (!api) throw new ErrorGoogleIdentity('Google Identity Services no está cargado.');
  return api;
}

export function inicializarGoogleIdentity(alRecibirCredencial: (idToken: string) => void): void {
  accounts().initialize({
    client_id: CLIENT_ID,
    callback: (respuesta) => {
      alRecibirCredencial(respuesta.credential);
    },
    // El diálogo se abre solo desde el botón: nada de entrar sin pedirlo.
    auto_select: false,
  });
}

/**
 * Pinta el botón de Google. Vacía el contenedor primero porque GIS no vuelve a
 * renderizar sobre un nodo que ya usó, y se llama de nuevo al cambiar de tema:
 * su botón no se puede estilar desde aquí (vive en un iframe de Google), así
 * que la única forma de que no quede blanco sobre fondo oscuro es repintarlo.
 */
export function pintarBotonGoogle(contenedor: HTMLElement, tema: Tema): void {
  contenedor.replaceChildren();
  accounts().renderButton(contenedor, {
    type: 'standard',
    theme: tema === 'dark' ? 'filled_black' : 'outline',
    size: 'large',
    text: 'continue_with',
    shape: 'rectangular',
    locale: 'es',
    width: contenedor.clientWidth || undefined,
  });
}

/** Al cerrar sesión: si no, GIS vuelve a entrar sola con la última cuenta. */
export function olvidarSeleccionGoogle(): void {
  window.google?.accounts.id.disableAutoSelect();
}
