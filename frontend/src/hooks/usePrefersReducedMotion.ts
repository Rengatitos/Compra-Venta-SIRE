import { useEffect, useState } from 'react';

const CONSULTA = '(prefers-reduced-motion: reduce)';

/**
 * Para animaciones que solo se pueden desactivar desde JS (las de Recharts, por
 * ejemplo). El CSS ya cubre el resto con su propia media query.
 */
export function usePrefersReducedMotion(): boolean {
  const [reducido, setReducido] = useState(
    () => window.matchMedia?.(CONSULTA).matches ?? false,
  );

  useEffect(() => {
    const media = window.matchMedia(CONSULTA);
    const alCambiar = (evento: MediaQueryListEvent) => {
      setReducido(evento.matches);
    };
    media.addEventListener('change', alCambiar);
    return () => {
      media.removeEventListener('change', alCambiar);
    };
  }, []);

  return reducido;
}
