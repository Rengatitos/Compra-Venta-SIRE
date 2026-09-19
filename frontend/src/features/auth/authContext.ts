import { createContext } from 'react';

export interface ContextoAuth {
  /** Correo de la persona autenticada, o null si no hay sesión. */
  correo: string | null;
  nombre: string | null;
  autenticado: boolean;
  /** Recibe el ID token de Google y guarda a cambio el JWT del backend. */
  iniciarSesionConGoogle: (idToken: string) => Promise<void>;
  salir: () => void;
}

export const ContextoAuthReact = createContext<ContextoAuth | null>(null);
