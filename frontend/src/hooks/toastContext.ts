import { createContext } from 'react';

export type TonoAviso = 'neutro' | 'exito' | 'error';

export interface Aviso {
  id: string;
  tono: TonoAviso;
  titulo: string;
  detalle?: string;
}

export interface ContextoAvisos {
  mostrar: (aviso: Omit<Aviso, 'id'>) => void;
  descartar: (id: string) => void;
  avisos: readonly Aviso[];
}

export const ContextoAvisosReact = createContext<ContextoAvisos | null>(null);
