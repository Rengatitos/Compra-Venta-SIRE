import { useContext } from 'react';

import { ContextoAvisosReact } from './toastContext';
import type { ContextoAvisos } from './toastContext';

export function useToast(): ContextoAvisos {
  const contexto = useContext(ContextoAvisosReact);
  if (!contexto) {
    throw new Error('useToast necesita estar dentro de <ToastProvider>.');
  }
  return contexto;
}
