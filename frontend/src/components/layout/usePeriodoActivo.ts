import { useMatch } from 'react-router';

import { esPeriodoValido } from '@/types/domain';

/**
 * El periodo que se está mirando, o `null` fuera de `/periodos/:periodo`.
 *
 * No sirve `useParams()`: `SideNav` lo pinta `AppShell`, que es la ruta padre, y
 * ahí los parámetros de las rutas hijas vienen vacíos. `useMatch` compara contra
 * la ubicación completa, y el `/*` final hace que un solo patrón cubra las tres
 * pantallas del periodo — un comodín casa también con cero segmentos, así que
 * `/periodos/202606` entra igual que `/periodos/202606/auditoria`.
 *
 * Se valida con el mismo `esPeriodoValido` que usa el resto del panel: la ruta
 * acepta cualquier cosa en `:periodo` y no tiene sentido anunciar un segundo
 * nivel para un periodo que no existe.
 */
export function usePeriodoActivo(): string | null {
  const coincidencia = useMatch('/periodos/:periodo/*');
  const periodo = coincidencia?.params.periodo;

  return periodo !== undefined && esPeriodoValido(periodo) ? periodo : null;
}
