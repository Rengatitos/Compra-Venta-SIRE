import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { ContextoAuthReact } from '@/features/auth/authContext';
import { ContextoEmpresasReact } from '@/features/empresas/empresasContext';
import { ContextoJobsReact } from '@/features/jobs/jobsContext';
import { NotificacionesMenu } from '@/features/jobs/NotificacionesMenu';
import type { JobResponse } from '@/types/api';

// `jsdom` no tiene canvas, así que el contraste se verifica en el navegador.
const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

vi.mock('@/api/jobs', () => ({
  listarJobs: (_ruc: string) => Promise.resolve([]),
  obtenerJob: () => Promise.reject(new Error('no debería consultarse en este test')),
}));

const RUC = '20608997106';

const JOB_EN_CURSO: JobResponse = {
  job_id: 'abc123',
  tipo: 'extraccion_detalles',
  estado: 'en_progreso',
  ruc: RUC,
  periodo: '202607',
  libro: null,
  progreso: { actual: 4, total: 10, mensaje: 'Extrayendo detalle', porcentaje: 40 },
  resultado: null,
  error: null,
  creado_en: '2026-08-29T20:41:00Z',
  actualizado_en: '2026-08-29T20:41:05Z',
};

function Envoltura({ children, job }: { children: ReactNode; job?: JobResponse }) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return (
    <MemoryRouter>
      <QueryClientProvider client={cliente}>
        <ToastProvider>
          <ContextoAuthReact.Provider
            value={{
              correo: 'prueba@example.com',
              nombre: 'Prueba',
              autenticado: true,
              iniciarSesionConGoogle: () => Promise.resolve(),
              salir: () => undefined,
            }}
          >
            {/* La campana lee el RUC activo con `useRuc()`, que ahora sale del
                contexto de empresas y no del de sesión. */}
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
                  seguidos: job ? [job.job_id] : [],
                  porId: job ? { [job.job_id]: job } : {},
                  seguir: () => undefined,
                  dejarDeSeguir: () => undefined,
                }}
              >
                {children}
              </ContextoJobsReact.Provider>
            </ContextoEmpresasReact.Provider>
          </ContextoAuthReact.Provider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe('menú de notificaciones', () => {
  it('el icono no basta: la campana dice con palabras cuántos procesos hay', () => {
    render(
      <Envoltura job={JOB_EN_CURSO}>
        <NotificacionesMenu />
      </Envoltura>,
    );

    expect(
      screen.getByRole('button', { name: /Notificaciones\. 1 proceso\(s\) en curso/ }),
    ).toBeInTheDocument();
  });

  it('abre el panel con el avance del proceso y el enlace al historial', async () => {
    render(
      <Envoltura job={JOB_EN_CURSO}>
        <NotificacionesMenu />
      </Envoltura>,
    );

    await userEvent.click(screen.getByRole('button', { name: /Notificaciones/ }));

    const panel = await screen.findByRole('dialog', { name: 'Procesos recientes' });
    expect(panel).toHaveTextContent('Detalle y PDF SUNAT · Julio 2026');
    expect(screen.getByRole('link', { name: /Ver historial de procesos/ })).toHaveAttribute(
      'href',
      '/procesos',
    );
  });

  it('el panel abierto no tiene violaciones de axe', async () => {
    const { container } = render(
      <Envoltura job={JOB_EN_CURSO}>
        <NotificacionesMenu />
      </Envoltura>,
    );

    await userEvent.click(screen.getByRole('button', { name: /Notificaciones/ }));
    await screen.findByRole('dialog', { name: 'Procesos recientes' });

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });
});
