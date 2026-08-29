import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { ContextoAuthReact } from '@/features/auth/authContext';
import { ContextoJobsReact } from '@/features/jobs/jobsContext';
import { NotificacionesMenu } from '@/features/jobs/NotificacionesMenu';
import type { JobResponse } from '@/types/api';

// `jsdom` no tiene canvas, así que el contraste se verifica en el navegador.
const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

vi.mock('@/api/jobs', () => ({
  listarJobs: () => Promise.resolve([]),
  obtenerJob: () => Promise.reject(new Error('no debería consultarse en este test')),
}));

const JOB_EN_CURSO: JobResponse = {
  job_id: 'abc123',
  tipo: 'extraccion_detalles',
  estado: 'en_progreso',
  ruc: '20608997106',
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
              ruc: '20608997106',
              autenticado: true,
              iniciarSesion: () => Promise.resolve(),
              salir: () => undefined,
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
    expect(panel).toHaveTextContent('Extracción de detalle · Julio 2026');
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
