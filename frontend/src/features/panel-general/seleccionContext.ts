import { createContext, useContext } from 'react';

export interface ContextoSeleccion {
  /** RUCs marcados en «Empresas» para lanzarlos desde «Procesamiento masivo». */
  seleccion: ReadonlySet<string>;
  setSeleccion: (seleccion: ReadonlySet<string>) => void;
}

export const ContextoSeleccionReact = createContext<ContextoSeleccion | null>(null);

export function useSeleccion(): ContextoSeleccion {
  const contexto = useContext(ContextoSeleccionReact);
  if (!contexto) {
    throw new Error('useSeleccion necesita estar dentro de <PanelGeneralShell>.');
  }
  return contexto;
}
