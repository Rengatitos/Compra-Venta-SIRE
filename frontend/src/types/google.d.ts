/**
 * Tipos mínimos de Google Identity Services.
 *
 * Se declaran a mano en vez de instalar `@types/google.one-tap` por dos motivos:
 * `tsconfig.app.json` fija `"types": ["vite/client", "vitest/globals"]`, así que
 * un paquete de tipos globales no se cargaría sin tocar ese array, mientras que
 * un `.d.ts` dentro de `src/` entra por el `include`; y el lint del proyecto usa
 * `recommendedTypeChecked`, con el que un `window.google` sin tipar dispara
 * `no-unsafe-member-access` y compañía. Solo se declara lo que se usa.
 */

interface CredencialGoogle {
  /** El ID token firmado por Google. Es lo único que viaja al backend. */
  credential: string;
  select_by?: string;
}

interface ConfigGoogleIdentity {
  client_id: string;
  callback: (respuesta: CredencialGoogle) => void;
  auto_select?: boolean;
  cancel_on_tap_outside?: boolean;
}

interface OpcionesBotonGoogle {
  type?: 'standard' | 'icon';
  theme?: 'outline' | 'filled_blue' | 'filled_black';
  size?: 'small' | 'medium' | 'large';
  text?: 'signin_with' | 'continue_with';
  shape?: 'rectangular' | 'pill';
  width?: number;
  locale?: string;
}

interface GoogleAccountsId {
  initialize: (config: ConfigGoogleIdentity) => void;
  renderButton: (contenedor: HTMLElement, opciones: OpcionesBotonGoogle) => void;
  disableAutoSelect: () => void;
}

interface Window {
  google?: {
    accounts: {
      id: GoogleAccountsId;
    };
  };
}
