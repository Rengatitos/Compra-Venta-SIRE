import { useEffect } from 'react';

const TITULO_FIJO = 'SIRE App';

/**
 * El título de la pestaña se mantiene fijo sin importar la ruta activa.
 *
 * La escritura va dentro de un efecto, no en el cuerpo del render: mutar
 * `document.title` mientras se renderiza es un efecto secundario impuro, se
 * ejecuta dos veces bajo StrictMode y puede repetirse en cada re-render.
 */
export function useDocumentTitle(_titulo: string): void {
  useEffect(() => {
    if (document.title !== TITULO_FIJO) {
      document.title = TITULO_FIJO;
    }
  }, []);
}
