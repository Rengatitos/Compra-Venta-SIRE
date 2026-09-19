import { useContext } from 'react';

import { ContextoEmpresasReact } from './empresasContext';
import type { ContextoEmpresas } from './empresasContext';

export function useEmpresas(): ContextoEmpresas {
  const contexto = useContext(ContextoEmpresasReact);
  if (!contexto) {
    throw new Error('useEmpresas necesita estar dentro de <EmpresaGate>.');
  }
  return contexto;
}

/**
 * Para pantallas que ya están detrás de `EmpresaGate` y por tanto siempre tienen
 * empresa activa. Evita comprobar null en cada componente.
 */
export function useRuc(): string {
  const { ruc } = useEmpresas();
  if (!ruc) {
    throw new Error('Se esperaba una empresa activa en esta ruta.');
  }
  return ruc;
}

/** Cómo se nombra una empresa en la interfaz. El nombre es opcional. */
export function etiquetaEmpresa(empresa: { ruc: string; nombre: string | null }): string {
  return empresa.nombre?.trim() ? `${empresa.nombre.trim()} — ${empresa.ruc}` : empresa.ruc;
}
