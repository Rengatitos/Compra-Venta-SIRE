import { JobsProvider } from '@/features/jobs/JobsProvider';

import { Armazon } from './Armazon';
import { SideNav } from './SideNav';
import { TopBar } from './TopBar';

/** Armazón de las pantallas de una empresa. La maqueta la pone `Armazon`. */
export function AppShell() {
  return (
    <JobsProvider>
      <Armazon
        barraLateral={<SideNav />}
        cabecera={<TopBar />}
        pie={
          <p>
            Se sincronizan los dos libros: compras (RCE) y ventas (RVIE). Cada uno se descarga,
            se extrae y se analiza por separado.
          </p>
        }
      />
    </JobsProvider>
  );
}
