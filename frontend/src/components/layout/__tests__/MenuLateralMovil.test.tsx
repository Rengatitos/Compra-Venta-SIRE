import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ContextoAuthReact } from '@/features/auth/authContext';
import { ContextoEmpresasReact } from '@/features/empresas/empresasContext';
import { ContextoJobsReact } from '@/features/jobs/jobsContext';

// La barra lateral monta la campana de procesos, que consulta el historial.
vi.mock('@/api/jobs', () => ({
  listarJobs: () => Promise.resolve([]),
  obtenerJob: () => Promise.reject(new Error('no debería consultarse en este test')),
}));

import { MenuLateralMovil } from '../MenuLateralMovil';

// `jsdom` no tiene canvas, así que el contraste se verifica en el navegador.
const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

function Envoltura({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter initialEntries={['/procesos']}>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <ContextoAuthReact.Provider
          value={{
            correo: 'prueba@example.com',
            nombre: 'Prueba',
            autenticado: true,
            iniciarSesionConGoogle: () => Promise.resolve(),
            salir: () => undefined,
          }}
        >
          <ContextoEmpresasReact.Provider
            value={{
              empresas: [],
              ruc: '20608997106',
              empresaActiva: null,
              cambiarEmpresa: () => undefined,
              recargar: () => undefined,
            }}
          >
            <ContextoJobsReact.Provider
              value={{
                seguidos: [],
                porId: {},
                seguir: () => undefined,
                dejarDeSeguir: () => undefined,
              }}
            >
              {children}
            </ContextoJobsReact.Provider>
          </ContextoEmpresasReact.Provider>
        </ContextoAuthReact.Provider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

/**
 * El botón se esconde por encima de 60rem y el viewport de `jsdom` mide 1024px,
 * así que con `css: true` la media query lo saca del árbol accesible. Se busca
 * con `hidden: true`: lo que se prueba aquí es la conducta del cajón, no en qué
 * anchos se ve el botón.
 */
function botonMenu() {
  return screen.getByRole('button', { name: 'Abrir el menú de navegación', hidden: true });
}

describe('cajón de navegación en móvil', () => {
  it('cerrado no aparece en el árbol accesible', () => {
    render(
      <Envoltura>
        <MenuLateralMovil />
      </Envoltura>,
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('el botón abre el cajón con la navegación dentro', async () => {
    render(
      <Envoltura>
        <MenuLateralMovil />
      </Envoltura>,
    );

    await userEvent.click(botonMenu());

    const cajon = screen.getByRole('dialog', { name: 'Navegación' });
    expect(cajon).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('navegar lo cierra', async () => {
    render(
      <Envoltura>
        <MenuLateralMovil />
      </Envoltura>,
    );

    await userEvent.click(botonMenu());
    await userEvent.click(screen.getByRole('link', { name: 'Ajustes' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('el aspa lo cierra', async () => {
    render(
      <Envoltura>
        <MenuLateralMovil />
      </Envoltura>,
    );

    await userEvent.click(botonMenu());
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar el menú de navegación' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('abierto no tiene violaciones de axe', async () => {
    const { container } = render(
      <Envoltura>
        <MenuLateralMovil />
      </Envoltura>,
    );

    await userEvent.click(botonMenu());

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });
});
