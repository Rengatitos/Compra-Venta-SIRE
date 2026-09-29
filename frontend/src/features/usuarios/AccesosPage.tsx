import { useQuery } from '@tanstack/react-query';
import { useId, useRef } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { useSearchParams } from 'react-router';

import { obtenerYo } from '@/api/usuarios';
import { ButtonLink } from '@/components/ui/Button';
import { EmptyState, Skeleton } from '@/components/ui/Feedback';
import { Marco } from '@/features/empresas/Marco';

import estilos from './AccesosPage.module.css';
import { CuentasApi } from './CuentasApi';
import { GestionAccesos } from './GestionAccesos';

type Vista = 'panel' | 'api';

const PESTANAS: readonly { vista: Vista; texto: string; detalle: string; icono: ReactNode }[] = [
  {
    vista: 'panel',
    texto: 'Panel',
    detalle: 'Personas con Google',
    icono: (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <circle cx="12" cy="8" r="3.5" />
        <path d="M5 19.5c.8-3.4 3.6-5.5 7-5.5s6.2 2.1 7 5.5" />
      </svg>
    ),
  },
  {
    vista: 'api',
    texto: 'API',
    detalle: 'Programas e integraciones',
    icono: (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="m8.5 7.5-4.5 4.5 4.5 4.5M15.5 7.5l4.5 4.5-4.5 4.5M13.5 5.5l-3 13" />
      </svg>
    ),
  },
];

/**
 * «Administrar cuentas»: dos áreas del mismo rango, una por pestaña. «Panel»
 * son las personas que entran con Google; «API», los programas que entran con
 * correo y contraseña. La pestaña va en la URL (`?vista=api`) para poder
 * enlazarla y para que recargar no devuelva a la primera.
 */
export function AccesosPage() {
  const yo = useQuery({ queryKey: ['yo'], queryFn: obtenerYo, staleTime: 60_000 });
  const [parametros, setParametros] = useSearchParams();
  const vista: Vista = parametros.get('vista') === 'api' ? 'api' : 'panel';
  const base = useId();
  const botones = useRef<(HTMLButtonElement | null)[]>([]);

  function elegir(nueva: Vista) {
    setParametros(nueva === 'panel' ? {} : { vista: nueva }, { replace: true });
  }

  // Patrón de pestañas de WAI-ARIA: las flechas mueven la selección y el foco.
  function alTeclear(evento: KeyboardEvent<HTMLButtonElement>) {
    const indice = PESTANAS.findIndex((p) => p.vista === vista);
    let siguiente: number | null = null;
    if (evento.key === 'ArrowRight') siguiente = (indice + 1) % PESTANAS.length;
    if (evento.key === 'ArrowLeft') siguiente = (indice - 1 + PESTANAS.length) % PESTANAS.length;
    if (evento.key === 'Home') siguiente = 0;
    if (evento.key === 'End') siguiente = PESTANAS.length - 1;
    const destino = siguiente === null ? undefined : PESTANAS[siguiente];
    if (!destino || siguiente === null) return;
    evento.preventDefault();
    elegir(destino.vista);
    botones.current[siguiente]?.focus();
  }

  return (
    <Marco
      titulo="Administrar cuentas"
      tituloOculto
      pie={
        <ButtonLink a="/" variante="fantasma" pequeno>
          Volver
        </ButtonLink>
      }
    >
      {yo.isPending ? <Skeleton lineas={3} etiqueta="Comprobando tu rol" /> : null}
      {yo.data && yo.data.rol !== 'admin' ? (
        <EmptyState
          titulo="Solo para administradores"
          texto="Pide a un administrador que te dé acceso o que cambie tu rol."
        />
      ) : null}
      {yo.data?.rol === 'admin' ? (
        <>
          <div className={estilos.pestanas} role="tablist" aria-label="Tipo de cuenta">
            {PESTANAS.map((pestana, i) => {
              const activa = pestana.vista === vista;
              return (
                <button
                  key={pestana.vista}
                  ref={(nodo) => {
                    botones.current[i] = nodo;
                  }}
                  type="button"
                  role="tab"
                  id={`${base}-pestana-${pestana.vista}`}
                  aria-selected={activa}
                  aria-controls={`${base}-vista-${pestana.vista}`}
                  tabIndex={activa ? 0 : -1}
                  className={estilos.pestana}
                  onClick={() => elegir(pestana.vista)}
                  onKeyDown={alTeclear}
                >
                  <span className={estilos.icono}>{pestana.icono}</span>
                  <span className={estilos.textos}>
                    <span className={estilos.nombre}>{pestana.texto}</span>
                    <span className={estilos.detalle}>{pestana.detalle}</span>
                  </span>
                </button>
              );
            })}
          </div>

          {/* Solo se monta la vista elegida: nunca las dos a la vez. */}
          <div
            role="tabpanel"
            id={`${base}-vista-${vista}`}
            aria-labelledby={`${base}-pestana-${vista}`}
            className={estilos.vista}
          >
            {vista === 'panel' ? <GestionAccesos /> : <CuentasApi />}
          </div>
        </>
      ) : null}
    </Marco>
  );
}
