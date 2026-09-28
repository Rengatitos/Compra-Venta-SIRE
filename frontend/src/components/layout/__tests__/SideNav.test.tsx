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

import { SideNav } from '../SideNav';

// `jsdom` no tiene canvas, así que el contraste se verifica en el navegador.
const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

const RUC = '20608997106';

function Envoltura({ children, ruta }: { children: ReactNode; ruta: string }) {
  return (
    <MemoryRouter initialEntries={[ruta]}>
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
              ruc: RUC,
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

function pintar(ruta: string, onNavegar?: () => void) {
  return render(
    <Envoltura ruta={ruta}>
      <SideNav onNavegar={onNavegar} />
    </Envoltura>,
  );
}

describe('barra lateral', () => {
  it('ofrece las cinco secciones', () => {
    pintar('/dashboard');

    for (const texto of [
      'Dashboard',
      'Periodos',
      'Procesos',
      'Maestro de cuentas',
      'Ajustes',
    ]) {
      expect(screen.getByRole('link', { name: texto })).toBeInTheDocument();
    }
  });

  it('marca solo la página en curso', () => {
    pintar('/dashboard');

    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: 'Periodos' })).not.toHaveAttribute('aria-current');
  });

  it('fuera de un periodo no hay segundo nivel que desplegar', () => {
    pintar('/periodos');

    expect(
      screen.queryByRole('button', { name: /Desplegar|Contraer/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Comprobantes' })).not.toBeInTheDocument();
  });

  it('el periodo que se está mirando abre su segundo nivel', () => {
    pintar('/periodos/202606/auditoria');

    expect(screen.getByRole('button', { name: 'Contraer Periodos' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByRole('link', { name: 'Comprobantes' })).toHaveAttribute(
      'href',
      '/periodos/202606',
    );
    expect(screen.getByRole('link', { name: 'Auditoría' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('el padre no reclama la página cuando la tiene un hijo', () => {
    pintar('/periodos/202606/auditoria');

    expect(screen.getByRole('link', { name: 'Periodos' })).not.toHaveAttribute('aria-current');
  });

  it('el segundo nivel se puede contraer a mano', async () => {
    pintar('/periodos/202606');

    await userEvent.click(screen.getByRole('button', { name: 'Contraer Periodos' }));

    expect(screen.getByRole('button', { name: 'Desplegar Periodos' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.queryByRole('link', { name: 'Auditoría' })).not.toBeInTheDocument();
  });

  it('el icono no basta: el desplegable se nombra con palabras', () => {
    pintar('/periodos/202606');

    expect(screen.getByRole('button', { name: 'Contraer Periodos' })).toBeInTheDocument();
  });

  it('no trae marca ni cuenta: solo la vuelta a las empresas', () => {
    pintar('/dashboard');

    expect(screen.getByRole('link', { name: 'Volver a las empresas' })).toHaveAttribute(
      'href',
      '/',
    );
    expect(screen.queryByRole('link', { name: /SIRE/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).not.toBeInTheDocument();
    expect(screen.queryByRole('switch', { name: 'Modo oscuro' })).not.toBeInTheDocument();
  });

  it('la vuelta a las empresas también cierra el cajón de móvil', async () => {
    const onNavegar = vi.fn();
    pintar('/dashboard', onNavegar);

    await userEvent.click(screen.getByRole('link', { name: 'Volver a las empresas' }));

    expect(onNavegar).toHaveBeenCalled();
  });

  it('avisa al navegar, que es como se cierra el cajón de móvil', async () => {
    const onNavegar = vi.fn();
    pintar('/periodos/202606', onNavegar);

    await userEvent.click(screen.getByRole('link', { name: 'Auditoría' }));

    expect(onNavegar).toHaveBeenCalled();
  });

  it('no tiene violaciones de axe', async () => {
    const { container } = pintar('/periodos/202606/reporte');

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });
});
