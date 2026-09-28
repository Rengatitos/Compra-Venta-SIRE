import { useMemo, useState, useSyncExternalStore } from 'react';

import { Armazon } from '@/components/layout/Armazon';
import { SideNavGeneral } from '@/components/layout/SideNavGeneral';
import { TopBar } from '@/components/layout/TopBar';
import { obtenerSesion, suscribirSesion } from '@/lib/session';

import { ContextoSeleccionReact } from './seleccionContext';
import { useResumenEmpresas } from './useResumenEmpresas';

/**
 * Armazón del panel de todas las empresas, en la raíz. Guarda la selección de
 * empresas para que sobreviva al ir de «Empresas» a «Procesamiento masivo».
 */
export function PanelGeneralShell() {
  const [seleccion, setSeleccion] = useState<ReadonlySet<string>>(new Set());
  const valor = useMemo(() => ({ seleccion, setSeleccion }), [seleccion]);

  const { nombres } = useResumenEmpresas();
  const activa = useSyncExternalStore(suscribirSesion, obtenerSesion, () => null)?.ruc ?? null;
  // Solo se ofrece volver a una empresa que sigue existiendo.
  const empresaActiva = activa ? (nombres.get(activa) ?? null) : null;

  return (
    <ContextoSeleccionReact.Provider value={valor}>
      <Armazon
        barraLateral={<SideNavGeneral empresaActiva={empresaActiva} />}
        cabecera={
          <TopBar
            campana={false}
            barra={(onNavegar) => (
              <SideNavGeneral empresaActiva={empresaActiva} onNavegar={onNavegar} />
            )}
          />
        }
      />
    </ContextoSeleccionReact.Provider>
  );
}
