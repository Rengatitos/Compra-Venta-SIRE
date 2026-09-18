import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { ContextoAuthReact } from '@/features/auth/authContext';
import { EmpresaGate } from '@/features/empresas/EmpresaGate';
import { guardarSesion, limpiarSesion } from '@/lib/session';
import type { EmpresaResponse } from '@/types/api';

// `jsdom` no tiene canvas, así que el contraste se verifica en el navegador.
const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

const mocks = vi.hoisted(() => ({ listarEmpresas: vi.fn() }));

vi.mock('@/api/empresas', () => ({
  listarEmpresas: mocks.listarEmpresas,
  crearEmpresa: vi.fn(),
}));

function empresa(ruc: string, nombre: string | null = null): EmpresaResponse {
  return {
    id: ruc,
    ruc,
    nombre,
    usuario: 'USUARIO',
    fecha_creacion: '2026-01-01T00:00:00Z',
    rubro: 'Comercio',
  };
}

const UNA = empresa('20603391692', 'Alfa');
const OTRA = empresa('20610202251', 'Beta');

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
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
            <Routes>
              <Route element={<EmpresaGate />}>
                <Route path="*" element={<p>Panel abierto</p>} />
              </Route>
            </Routes>
          </ContextoAuthReact.Provider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('elección de empresa', () => {
  beforeEach(() => {
    mocks.listarEmpresas.mockReset();
    guardarSesion({ token: 'jwt', correo: 'prueba@example.com', ruc: null });
  });

  afterEach(() => {
    limpiarSesion();
  });

  it('con una sola empresa entra directo, sin preguntar', async () => {
    mocks.listarEmpresas.mockResolvedValue([UNA]);

    montar();

    expect(await screen.findByText('Panel abierto')).toBeInTheDocument();
  });

  it('con varias y ninguna elegida, pide elegir', async () => {
    // No se autoselecciona «la primera»: con dos cuentas abiertas se podría
    // sincronizar o borrar datos creyendo estar en la otra.
    mocks.listarEmpresas.mockResolvedValue([UNA, OTRA]);

    montar();

    expect(await screen.findByRole('heading', { name: 'Elige una empresa' })).toBeInTheDocument();
    expect(screen.queryByText('Panel abierto')).not.toBeInTheDocument();
  });

  it('con varias y una recordada, entra en la recordada', async () => {
    mocks.listarEmpresas.mockResolvedValue([UNA, OTRA]);
    guardarSesion({ token: 'jwt', correo: 'prueba@example.com', ruc: OTRA.ruc });

    montar();

    expect(await screen.findByText('Panel abierto')).toBeInTheDocument();
  });

  it('descarta una empresa recordada que ya no existe', async () => {
    // Se pudo borrar desde otra sesión; usarla a ciegas dejaría el panel en un
    // 404 permanente.
    mocks.listarEmpresas.mockResolvedValue([UNA, OTRA]);
    guardarSesion({ token: 'jwt', correo: 'prueba@example.com', ruc: '20000000000' });

    montar();

    expect(await screen.findByRole('heading', { name: 'Elige una empresa' })).toBeInTheDocument();
  });

  it('sin ninguna empresa ofrece dar de alta la primera ahí mismo', async () => {
    // El formulario va incrustado y no como enlace: `/empresas/nueva` vive
    // dentro del panel, que a su vez exige una empresa activa.
    mocks.listarEmpresas.mockResolvedValue([]);

    montar();

    expect(
      await screen.findByRole('heading', { name: 'Todavía no hay ninguna empresa' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Registrar empresa' })).toBeInTheDocument();
  });

  it('si la consulta falla, ofrece reintentar sin perder la sesión', async () => {
    mocks.listarEmpresas.mockRejectedValue(new Error('sin red'));

    montar();

    expect(await screen.findByText('Error al consultar el servidor')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument();
  });

  it('la pantalla de elección no tiene violaciones de axe', async () => {
    mocks.listarEmpresas.mockResolvedValue([UNA, OTRA]);

    const { container } = montar();
    await screen.findByRole('heading', { name: 'Elige una empresa' });

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });

  it('el estado vacío no tiene violaciones de axe', async () => {
    mocks.listarEmpresas.mockResolvedValue([]);

    const { container } = montar();
    await screen.findByRole('heading', { name: 'Todavía no hay ninguna empresa' });

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });
});
