/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base de la API. Vacío usa /api/v1 y, en desarrollo, el proxy de Vite. */
  readonly VITE_API_BASE_URL?: string;
  /**
   * Client ID del cliente OAuth de Google (tipo «aplicación web»). No es un
   * secreto: viaja en el bundle, y lo que protege el acceso son los «Orígenes
   * de JavaScript autorizados» de ese cliente en Google Cloud. Sin él, /login
   * no puede pintar el botón y lo dice en pantalla.
   */
  readonly VITE_GOOGLE_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
