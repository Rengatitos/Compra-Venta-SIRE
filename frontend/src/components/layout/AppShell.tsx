import { useQuery } from '@tanstack/react-query';
import { Suspense } from 'react';
import { Outlet } from 'react-router';

import { obtenerEmpresa } from '@/api/empresas';
import { Skeleton } from '@/components/ui/Feedback';
import { useAuth, useRuc } from '@/features/auth/useAuth';
import { JobsProvider } from '@/features/jobs/JobsProvider';

import { AmbientBackground } from './AmbientBackground';
import estilos from './AppShell.module.css';
import { SideNav } from './SideNav';
import { TopBar } from './TopBar';

/**
 * Armazón de las rutas autenticadas: landmarks semánticos (`header`, `nav`,
 * `main`, `footer`), enlace de salto al contenido y el fondo ambiental.
 *
 * `JobsProvider` se monta aquí y no en `App`: sondea `GET /jobs/{id}`, así que
 * solo debe existir dentro de la zona ya autenticada.
 */
export function AppShell() {
  const ruc = useRuc();
  const { salir } = useAuth();

  const empresa = useQuery({
    queryKey: ['empresa', ruc],
    queryFn: () => obtenerEmpresa(ruc),
    staleTime: 5 * 60_000,
  });

  return (
    <JobsProvider>
      <AmbientBackground />
      <a className={estilos.saltar} href="#contenido">
        Saltar al contenido
      </a>

      <div className={estilos.armazon}>
        <header className={estilos.cabecera}>
          <TopBar ruc={ruc} rubro={empresa.data?.rubro ?? null} onSalir={salir} />
        </header>

        <nav className={estilos.nav} aria-label="Secciones de la aplicación">
          <SideNav />
        </nav>

        <main className={estilos.contenido} id="contenido">
          <Suspense fallback={<Skeleton lineas={5} etiqueta="Cargando la sección" />}>
            <Outlet />
          </Suspense>
        </main>

        <footer className={estilos.pie}>
          <p>
            Solo se sincroniza el libro de compras (RCE). El registro de ventas (RVIE) todavía no
            está disponible en la API.
          </p>
        </footer>
      </div>
    </JobsProvider>
  );
}
