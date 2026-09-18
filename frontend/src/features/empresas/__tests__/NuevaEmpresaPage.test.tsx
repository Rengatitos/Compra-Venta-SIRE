import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { NuevaEmpresaPage } from '@/features/empresas/NuevaEmpresaPage';
import { guardarSesion, limpiarSesion, obtenerSesion } from '@/lib/session';
import type { EmpresaResponse } from '@/types/api';

const mocks = vi.hoisted(() => ({ crearEmpresa: vi.fn() }));

vi.mock('@/api/empresas', () => ({
  crearEmpresa: mocks.crearEmpresa,
  listarEmpresas: vi.fn(),
}));

const CREADA: EmpresaResponse = {
  id: '1',
  ruc: '20999999999',
  nombre: 'Nueva',
  usuario: 'USUARIO',
  fecha_creacion: null,
  rubro: null,
};

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/empresas/nueva']}>
      <QueryClientProvider client={cliente}>
        <ToastProvider>
          <Routes>
            <Route path="/empresas/nueva" element={<NuevaEmpresaPage />} />
            <Route path="/" element={<p>Panel</p>} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('alta de empresa', () => {
  beforeEach(() => {
    mocks.crearEmpresa.mockReset();
    guardarSesion({ token: 'jwt', correo: 'prueba@example.com', ruc: '20603391692' });
  });

  afterEach(() => {
    limpiarSesion();
  });

  it('ofrece volver al panel sin cerrar la sesión', () => {
    montar();

    expect(screen.getByRole('link', { name: 'Volver al panel' })).toHaveAttribute('href', '/');
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).not.toBeInTheDocument();
  });

  it('al crear deja activa la empresa nueva y vuelve al panel', async () => {
    // Es lo que se venía a hacer: entrar en ella, no tener que buscarla después
    // en el selector.
    mocks.crearEmpresa.mockResolvedValue(CREADA);
    montar();

    await userEvent.type(screen.getByLabelText(/RUC/), CREADA.ruc);
    await userEvent.type(screen.getByLabelText(/Usuario SOL/), 'USUARIO');
    await userEvent.type(screen.getByLabelText(/Contraseña SOL/), 'clave');
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(await screen.findByText('Panel')).toBeInTheDocument();
    expect(obtenerSesion()?.ruc).toBe(CREADA.ruc);
  });

  it('un RUC ya registrado apunta al selector en vez de dejar al usuario atascado', async () => {
    const { ApiError } = await import('@/lib/http');
    mocks.crearEmpresa.mockRejectedValue(new ApiError(409, 'Ya existe una empresa con ese RUC'));
    montar();

    await userEvent.type(screen.getByLabelText(/RUC/), CREADA.ruc);
    await userEvent.type(screen.getByLabelText(/Usuario SOL/), 'USUARIO');
    await userEvent.type(screen.getByLabelText(/Contraseña SOL/), 'clave');
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('búscalo en el selector de empresas');
  });
});
