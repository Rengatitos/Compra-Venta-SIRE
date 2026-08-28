import { useCallback, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { ContextoAvisosReact } from '@/hooks/toastContext';
import type { Aviso } from '@/hooks/toastContext';

import estilos from './Toast.module.css';

const DURACION_MS = 7000;

const CLASE_TONO: Record<Aviso['tono'], string> = {
  neutro: '',
  exito: estilos.exito ?? '',
  error: estilos.error ?? '',
};

/**
 * Avisos transitorios. Los de error usan `role="alert"` (interrumpen) y el resto
 * `role="status"` (esperan una pausa), que es la distinción que espera un lector
 * de pantalla.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const contador = useRef(0);
  const temporizadores = useRef(new Map<string, number>());

  const descartar = useCallback((id: string) => {
    setAvisos((previos) => previos.filter((aviso) => aviso.id !== id));
    const temporizador = temporizadores.current.get(id);
    if (temporizador !== undefined) {
      window.clearTimeout(temporizador);
      temporizadores.current.delete(id);
    }
  }, []);

  const mostrar = useCallback(
    (aviso: Omit<Aviso, 'id'>) => {
      contador.current += 1;
      const id = `aviso-${contador.current}`;
      setAvisos((previos) => [...previos, { ...aviso, id }]);
      temporizadores.current.set(
        id,
        window.setTimeout(() => {
          descartar(id);
        }, DURACION_MS),
      );
    },
    [descartar],
  );

  const valor = useMemo(() => ({ avisos, mostrar, descartar }), [avisos, mostrar, descartar]);

  return (
    <ContextoAvisosReact.Provider value={valor}>
      {children}
      <div className={estilos.region} role="region" aria-label="Notificaciones">
        {avisos.map((aviso) => (
          <div
            key={aviso.id}
            className={`${estilos.aviso} ${CLASE_TONO[aviso.tono]}`}
            role={aviso.tono === 'error' ? 'alert' : 'status'}
          >
            <div className={estilos.cuerpo}>
              <p className={estilos.titulo}>{aviso.titulo}</p>
              {aviso.detalle ? <p className={estilos.detalle}>{aviso.detalle}</p> : null}
            </div>
            <button
              type="button"
              className={estilos.cerrar}
              onClick={() => descartar(aviso.id)}
            >
              <span aria-hidden="true">×</span>
              <span className="visually-hidden">Descartar aviso</span>
            </button>
          </div>
        ))}
      </div>
    </ContextoAvisosReact.Provider>
  );
}
