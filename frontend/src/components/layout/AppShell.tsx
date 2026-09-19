import { Suspense } from 'react';
import { Outlet } from 'react-router';

import { Skeleton } from '@/components/ui/Feedback';
import { JobsProvider } from '@/features/jobs/JobsProvider';

import { AmbientBackground } from './AmbientBackground';
import estilos from './AppShell.module.css';
import { SideNav } from './SideNav';
import { TopBar } from './TopBar';

/**
 * Armazón de las rutas autenticadas.
 *
 * La barra lateral ocupa una columna propia de alto completo y se queda fija; la
 * cabecera, el contenido y el pie viven en una segunda columna de flujo normal.
 * Ese reparto no es decorativo: un elemento `sticky` no puede salir de su bloque
 * contenedor, y el bloque contenedor de un ítem de rejilla es su área. Una
 * cabecera en una fila `auto` mide exactamente lo que su área, así que no tiene
 * dónde moverse y `sticky` no hace nada. Metida en una columna de flujo normal
 * sí tiene recorrido.
 */
export function AppShell() {
  return (
    <JobsProvider>
      <AmbientBackground />
      <a className={estilos.saltar} href="#contenido">
        Saltar al contenido
      </a>

      <div className={estilos.armazon}>
        <aside className={estilos.nav} aria-label="Barra lateral">
          <SideNav />
        </aside>

        <div className={estilos.columna}>
          <header className={estilos.cabecera}>
            <TopBar />
          </header>

          <main className={estilos.contenido} id="contenido">
            <Suspense fallback={<Skeleton lineas={5} etiqueta="Cargando la sección" />}>
              <Outlet />
            </Suspense>
          </main>

          <footer className={estilos.pie}>
            <p>
              Se sincronizan los dos libros: compras (RCE) y ventas (RVIE). Cada uno se
              descarga, se extrae y se analiza por separado.
            </p>
          </footer>
        </div>
      </div>
    </JobsProvider>
  );
}
