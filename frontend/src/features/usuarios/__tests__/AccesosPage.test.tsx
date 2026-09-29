import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { AccesosPage } from '@/features/usuarios/AccesosPage';

const mocks = vi.hoisted(() => ({
  obtenerYo: vi.fn(),
  listarUsuarios: vi.fn(),
  listarCuentasApi: vi.fn(),
}));

vi.mock('@/api/usuarios', () => ({
  obtenerYo: mocks.obtenerYo,
  listarUsuarios: mocks.listarUsuarios,
  agregarUsuario: vi.fn(),
  cambiarRol: vi.fn(),
  quitarUsuario: vi.fn(),
}));
vi.mock('@/api/cuentasApi', () => ({
  listarCuentasApi: mocks.listarCuentasApi,
  crearCuentaApi: vi.fn(),
  regenerarCuentaApi: vi.fn(),
  eliminarCuentaApi: vi.fn(),
}));
vi.mock('@/features/usuarios/useEsAdmin', () => ({ useEsAdmin: () => true }));

const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

function montar(ruta = '/accesos') {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <QueryClientProvider client={cliente}>
        <ToastProvider>
          <AccesosPage />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('Administrar cuentas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.obtenerYo.mockResolvedValue({ email: 'a@x.pe', rol: 'admin' });
    mocks.listarUsuarios.mockResolvedValue([
      { email: 'a@x.pe', rol: 'admin', fijo: true, agregado_por: null, agregado_en: null },
    ]);
    mocks.listarCuentasApi.mockResolvedValue([]);
  });

  it('abre en «Panel» y muestra solo las cuentas de Google', async () => {
    const { container } = montar();

    const panel = await screen.findByRole('tab', { name: /Panel/ });
    expect(panel).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /API/ })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('heading', { name: 'Cuentas con acceso' })).toBeInTheDocument();
    expect(await screen.findByText('a@x.pe')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Cuentas de API' })).not.toBeInTheDocument();
    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });

  it('al elegir «API» cambia la vista entera', async () => {
    montar();

    await userEvent.click(await screen.findByRole('tab', { name: /API/ }));

    expect(screen.getByRole('tab', { name: /API/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('heading', { name: 'Cuentas de API' })).toBeInTheDocument();
    expect(screen.getByText(/se muestran una sola vez/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Cuentas con acceso' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Correo de Google/)).not.toBeInTheDocument();
  });

  it('las flechas mueven entre pestañas y `?vista=api` abre directo en API', async () => {
    montar('/accesos?vista=api');

    const api = await screen.findByRole('tab', { name: /API/ });
    expect(api).toHaveAttribute('aria-selected', 'true');

    api.focus();
    await userEvent.keyboard('{ArrowLeft}');
    expect(screen.getByRole('tab', { name: /Panel/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /Panel/ })).toHaveFocus();
  });
});
