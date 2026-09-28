import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { CuentasApi } from '@/features/usuarios/CuentasApi';
import type { CuentaApi } from '@/types/api';

const mocks = vi.hoisted(() => ({
  listarCuentasApi: vi.fn(),
  crearCuentaApi: vi.fn(),
  regenerarCuentaApi: vi.fn(),
  eliminarCuentaApi: vi.fn(),
}));

vi.mock('@/api/cuentasApi', () => mocks);

const CUENTA: CuentaApi = {
  email: 'administrador@apaclla.au.pe',
  rol: 'admin',
  vigencia_dias: 90,
  expira_en: '2026-12-27T00:00:00Z',
  vigente: true,
  creada_por: 'puff27oo@gmail.com',
  creada_en: '2026-09-28T00:00:00Z',
  clave_generada_en: '2026-09-28T00:00:00Z',
  ultimo_uso_en: null,
};

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <ToastProvider>
        <CuentasApi />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe('cuentas de API', () => {
  beforeEach(() => {
    for (const mock of Object.values(mocks)) mock.mockReset();
    mocks.listarCuentasApi.mockResolvedValue([]);
  });

  it('al crearla muestra la contraseña y el curl una sola vez', async () => {
    mocks.crearCuentaApi.mockResolvedValue({ cuenta: CUENTA, password: 'clave-generada-XYZ' });
    montar();

    await userEvent.type(screen.getByLabelText(/Correo de la cuenta/), CUENTA.email);
    await userEvent.selectOptions(screen.getByLabelText(/^Rol/), 'admin');
    await userEvent.click(screen.getByRole('button', { name: 'Crear cuenta y generar contraseña' }));

    expect(mocks.crearCuentaApi).toHaveBeenCalledWith(CUENTA.email, 'admin', 90);
    expect(await screen.findByText('clave-generada-XYZ')).toBeInTheDocument();
    expect(screen.getByText(/\/api\/v1\/auth\/token/, { selector: 'pre' })).toHaveTextContent(
      '"password": "clave-generada-XYZ"',
    );

    await userEvent.click(screen.getByRole('button', { name: 'Ya la guardé' }));
    expect(screen.queryByText('clave-generada-XYZ')).not.toBeInTheDocument();
  });

  it('lista las cuentas sin contraseña y permite regenerarla', async () => {
    mocks.listarCuentasApi.mockResolvedValue([CUENTA]);
    mocks.regenerarCuentaApi.mockResolvedValue({ cuenta: CUENTA, password: 'otra-clave' });
    montar();

    expect(await screen.findByText(CUENTA.email)).toBeInTheDocument();
    expect(screen.getByText('Vigente')).toBeInTheDocument();
    expect(screen.getByText(/Sin usar/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Nueva contraseña' }));
    expect(mocks.regenerarCuentaApi).toHaveBeenCalledWith(CUENTA.email);
    expect(await screen.findByText('otra-clave')).toBeInTheDocument();
  });
});
