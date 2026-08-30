import { createContext } from 'react';

export type TonoAviso = 'neutro' | 'exito' | 'error';

/** Enlace opcional del aviso, para llevar a donde ocurre lo que anuncia. */
export interface AccionAviso {
  texto: string;
  a: string;
}

export interface Aviso {
  id: string;
  tono: TonoAviso;
  titulo: string;
  detalle?: string;
  accion?: AccionAviso;
}

export interface ContextoAvisos {
  mostrar: (aviso: Omit<Aviso, 'id'>) => void;
  descartar: (id: string) => void;
  avisos: readonly Aviso[];
}

export const ContextoAvisosReact = createContext<ContextoAvisos | null>(null);
