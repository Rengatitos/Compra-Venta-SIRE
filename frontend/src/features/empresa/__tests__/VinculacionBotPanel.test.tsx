import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';

import { VinculacionBotPanel } from '../VinculacionBotPanel';

const RUC = '20603391692';
const mocks = vi.hoisted(() => ({ generar: vi.fn() }));
vi.mock('@/api/empresas', () => ({ generarCodigoVinculacion: mocks.generar }));

const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

function Envoltura({ children }: { children: ReactNode }) {
  const cliente = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={cliente}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  vi.resetAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('VinculacionBotPanel', () => {
  it('explica los pasos con el RUC antes de generar nada', () => {
    render(<VinculacionBotPanel ruc={RUC} />, { wrapper: Envoltura });

    expect(screen.getByRole('heading', { name: 'Conectar Apaclla Bot' })).toBeInTheDocument();
    expect(screen.getByText(RUC)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Comprobantes externos' })).toHaveAttribute(
      'href',
      '/externos',
    );
  });

  it('genera el código y lo muestra en la tarjeta con su cuenta regresiva', async () => {
    const expira = new Date(Date.now() + 10 * 60 * 1000).toISOString();
    mocks.generar.mockResolvedValue({ codigo: '483921', expira_en: expira });

    const { container } = render(<VinculacionBotPanel ruc={RUC} />, { wrapper: Envoltura });
    await userEvent.click(screen.getByRole('button', { name: 'Generar código' }));

    expect(await screen.findByText('Código 4 8 3 9 2 1')).toBeInTheDocument();
    expect(mocks.generar).toHaveBeenCalledWith(RUC);
    expect(screen.getByText('Código activo')).toBeInTheDocument();
    expect(screen.getByRole('timer')).toHaveTextContent(/Vence en (9:5\d|10:00)/);
    expect(screen.getByRole('button', { name: 'Copiar código' })).toBeInTheDocument();
    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });

  it('cuando vence ofrece generar otro', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const expira = new Date(Date.now() + 2000).toISOString();
    mocks.generar.mockResolvedValue({ codigo: '483921', expira_en: expira });

    render(<VinculacionBotPanel ruc={RUC} />, { wrapper: Envoltura });
    await userEvent.click(screen.getByRole('button', { name: 'Generar código' }));
    await screen.findByRole('timer');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(screen.getByRole('timer')).toHaveTextContent('Este código venció. Genera otro.');
    expect(screen.getByRole('button', { name: 'Generar otro' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Copiar código' })).not.toBeInTheDocument();
  });
});
