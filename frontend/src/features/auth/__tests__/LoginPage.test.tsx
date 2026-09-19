import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { LoginPage } from '@/features/auth/LoginPage';
import { ApiError } from '@/lib/http';
import { limpiarSesion } from '@/lib/session';
import type { TokenResponse } from '@/types/api';

// `jsdom` no tiene canvas, así que el contraste se verifica en el navegador.
const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

/**
 * Todo Google Identity Services está simulado. Es la razón principal por la que
 * el acceso a GIS vive en un módulo propio: en jsdom un `<script src>` externo
 * no se ejecuta nunca, así que sin este doble los tests dependerían de la red.
 */
let alRecibirCredencial: ((idToken: string) => void) | null = null;

const mocks = vi.hoisted(() => ({
  hayClientId: vi.fn(() => true),
  cargarGoogleIdentity: vi.fn(() => Promise.resolve()),
  pintarBotonGoogle: vi.fn(),
  olvidarSeleccionGoogle: vi.fn(),
  iniciarSesionConGoogle: vi.fn<(idToken: string) => Promise<TokenResponse>>(),
}));

vi.mock('@/lib/google', () => ({
  hayClientId: mocks.hayClientId,
  cargarGoogleIdentity: mocks.cargarGoogleIdentity,
  pintarBotonGoogle: mocks.pintarBotonGoogle,
  olvidarSeleccionGoogle: mocks.olvidarSeleccionGoogle,
  inicializarGoogleIdentity: (callback: (idToken: string) => void) => {
    alRecibirCredencial = callback;
  },
}));

vi.mock('@/api/auth', () => ({
  iniciarSesionConGoogle: (idToken: string) => mocks.iniciarSesionConGoogle(idToken),
}));

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <QueryClientProvider client={cliente}>
        <ToastProvider>
          <AuthProvider>
            <LoginPage />
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('pantalla de acceso', () => {
  beforeEach(() => {
    limpiarSesion();
    alRecibirCredencial = null;
    mocks.hayClientId.mockReturnValue(true);
    mocks.cargarGoogleIdentity.mockResolvedValue(undefined);
    mocks.pintarBotonGoogle.mockClear();
    mocks.iniciarSesionConGoogle.mockReset();
  });

  it('pinta el botón de Google cuando todo está en su sitio', async () => {
    montar();

    await waitFor(() => {
      expect(mocks.pintarBotonGoogle).toHaveBeenCalled();
    });
  });

  it('sin client id lo dice en vez de pintar un botón muerto', async () => {
    mocks.hayClientId.mockReturnValue(false);

    montar();

    expect(await screen.findByText(/Falta configurar el acceso con Google/)).toBeInTheDocument();
    expect(mocks.pintarBotonGoogle).not.toHaveBeenCalled();
  });

  it('si el script de Google no carga, ofrece reintentar', async () => {
    mocks.cargarGoogleIdentity.mockRejectedValue(new Error('bloqueado'));

    montar();

    expect(await screen.findByText(/No se pudo cargar el acceso con Google/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
  });

  it('cambia el ID token de Google por la sesión del backend', async () => {
    mocks.iniciarSesionConGoogle.mockResolvedValue({
      access_token: 'jwt',
      token_type: 'bearer',
      usuario: { email: 'prueba@example.com', nombre: 'Prueba', foto: null },
    });
    montar();
    await waitFor(() => {
      expect(alRecibirCredencial).not.toBeNull();
    });

    await act(() => {
      alRecibirCredencial?.('id-token-de-google');
      return Promise.resolve();
    });

    expect(mocks.iniciarSesionConGoogle).toHaveBeenCalledWith('id-token-de-google');
  });

  it('una cuenta sin acceso ve por toast el motivo que da el backend', async () => {
    // El 403 del backend distingue «esta cuenta no tiene acceso» de un fallo de
    // red o un token inválido; ese matiz es lo que tiene que llegar a pantalla.
    // Sale por toast, como el resto del panel, y no dentro de la tarjeta.
    mocks.iniciarSesionConGoogle.mockRejectedValue(
      new ApiError(403, 'Esta cuenta de Google no tiene acceso al panel'),
    );
    const { container } = montar();
    await waitFor(() => {
      expect(alRecibirCredencial).not.toBeNull();
    });

    await act(() => {
      alRecibirCredencial?.('id-token-de-google');
      return Promise.resolve();
    });

    const aviso = await screen.findByRole('alert');
    expect(aviso).toHaveTextContent('Esta cuenta de Google no tiene acceso al panel');
    // Dentro de la región de notificaciones, no de la tarjeta de acceso.
    expect(container.querySelector('main')?.contains(aviso)).toBe(false);
  });

  it('no tiene violaciones de axe', async () => {
    const { container } = montar();
    await waitFor(() => {
      expect(mocks.pintarBotonGoogle).toHaveBeenCalled();
    });

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });
});
