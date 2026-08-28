/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base de la API. Vacío usa /api/v1 y, en desarrollo, el proxy de Vite. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
