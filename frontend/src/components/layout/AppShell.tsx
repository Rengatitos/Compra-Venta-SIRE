import { useQuery } from '@tanstack/react-query';
import { Suspense } from 'react';
import { Outlet } from 'react-router';

import { obtenerEmpresa } from '@/api/empresas';
import { Skeleton } from '@/components/ui/Feedback';
import { useAuth, useRuc } from '@/features/auth/useAuth';

import { AmbientBackground } from './AmbientBackground';
import estilos from './AppShell.module.css';
import { SideNav } from './SideNav';
import { TopBar } from './TopBar';

/**
 * Armazón de las rutas autenticadas: landmarks semánticos (`header`, `nav`,
 * `main`, `footer`), enlace de salto al contenido y el fondo ambiental.
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
    <>
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
    </>
  );
}
