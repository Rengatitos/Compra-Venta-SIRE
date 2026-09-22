import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, within } from '@testing-library/react';
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
    <QueryClientProvider client={cliente}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
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
  it('genera el código y lo muestra con su cuenta regresiva', async () => {
    const expira = new Date(Date.now() + 10 * 60 * 1000).toISOString();
    mocks.generar.mockResolvedValue({ codigo: '483921', expira_en: expira });

    const { container } = render(<VinculacionBotPanel ruc={RUC} />, { wrapper: Envoltura });
    await userEvent.click(screen.getByRole('button', { name: 'Generar código' }));

    const dialogo = await screen.findByRole('dialog');
    expect(mocks.generar).toHaveBeenCalledWith(RUC);
    expect(within(dialogo).getByText('483921')).toBeInTheDocument();
    expect(
      within(dialogo).getByText(`En Apaclla Bot, escribe el RUC ${RUC} y este código.`),
    ).toBeInTheDocument();
    expect(within(dialogo).getByRole('timer')).toHaveTextContent(/Vence en (9:5\d|10:00)/);
    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });

  it('cuando vence ofrece generar otro', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const expira = new Date(Date.now() + 2000).toISOString();
    mocks.generar.mockResolvedValue({ codigo: '483921', expira_en: expira });

    render(<VinculacionBotPanel ruc={RUC} />, { wrapper: Envoltura });
    await userEvent.click(screen.getByRole('button', { name: 'Generar código' }));
    const dialogo = await screen.findByRole('dialog');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(within(dialogo).getByRole('timer')).toHaveTextContent(
      'Este código venció. Genera otro.',
    );
    expect(within(dialogo).getByRole('button', { name: 'Generar otro' })).toBeInTheDocument();
  });
});
