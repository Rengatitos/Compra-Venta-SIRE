import { Suspense } from 'react';
import type { ReactNode } from 'react';
import { Outlet } from 'react-router';

import { Skeleton } from '@/components/ui/Feedback';

import { AmbientBackground } from './AmbientBackground';
import estilos from './AppShell.module.css';

interface Props {
  /** Contenido de la tarjeta lateral de escritorio. */
  barraLateral: ReactNode;
  /** Cabecera que solo aparece por debajo de 60rem (cajón y, si toca, campana). */
  cabecera: ReactNode;
  pie?: ReactNode;
}

/**
 * Maqueta de las pantallas con barra lateral: la de una empresa (`AppShell`) y
 * la de todas (`PanelGeneralShell`).
 *
 * La barra lateral ocupa una columna propia de alto completo y se queda fija; la
 * cabecera, el contenido y el pie viven en una segunda columna de flujo normal.
 * Ese reparto no es decorativo: un elemento `sticky` no puede salir de su bloque
 * contenedor, y el bloque contenedor de un ítem de rejilla es su área. Una
 * cabecera en una fila `auto` mide exactamente lo que su área, así que no tiene
 * dónde moverse y `sticky` no hace nada. Metida en una columna de flujo normal
 * sí tiene recorrido.
 */
export function Armazon({ barraLateral, cabecera, pie }: Props) {
  return (
    <>
      <AmbientBackground />
      <a className={estilos.saltar} href="#contenido">
        Saltar al contenido
      </a>

      <div className={estilos.armazon}>
        <aside className={estilos.nav} aria-label="Barra lateral">
          {barraLateral}
        </aside>

        <div className={estilos.columna}>
          <header className={estilos.cabecera}>{cabecera}</header>

          <main className={estilos.contenido} id="contenido">
            <Suspense fallback={<Skeleton lineas={5} etiqueta="Cargando la sección" />}>
              <Outlet />
            </Suspense>
          </main>

          {pie ? <footer className={estilos.pie}>{pie}</footer> : null}
        </div>
      </div>
    </>
  );
}
