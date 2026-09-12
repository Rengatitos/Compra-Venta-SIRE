import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/http';

import { DescargarPdfsButton } from '../DescargarPdfsButton';

const mocks = vi.hoisted(() => ({
  zip: vi.fn(),
  mostrar: vi.fn(),
}));
vi.mock('@/api/pdfs', () => ({
  descargarZipSunatCompleto: mocks.zip,
}));
vi.mock('@/hooks/useToast', () => ({ useToast: () => ({ mostrar: mocks.mostrar }) }));

beforeEach(() => {
  vi.resetAllMocks();
  mocks.zip.mockResolvedValue(0);
});

async function descargar() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DescargarPdfsButton ruc="20123456789" periodo="202608" libro="ventas" />
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole('button', { name: /ZIP de PDFs SUNAT/ }));
}

it('descarga desde SUNAT ambos registros y comunica el resultado', async () => {
  await descargar();
  await waitFor(() =>
    expect(mocks.zip).toHaveBeenCalledWith(
      '20123456789',
      '202608',
      'ventas',
      expect.any(Function),
    ),
  );
  await waitFor(() =>
    expect(mocks.mostrar).toHaveBeenCalledWith(expect.objectContaining({ tono: 'exito' })),
  );
});

it('avisa cuando SUNAT no entrega todos los PDFs', async () => {
  mocks.zip.mockResolvedValue(2);
  await descargar();
  await waitFor(() =>
    expect(mocks.mostrar).toHaveBeenCalledWith(
      expect.objectContaining({
        tono: 'neutro',
        titulo: 'ZIP descargado con comprobantes faltantes',
      }),
    ),
  );
  const aviso = mocks.mostrar.mock.calls[0]?.[0] as { detalle?: string } | undefined;
  expect(aviso?.detalle).toContain('2 PDFs');
  expect(aviso?.detalle).toContain('faltantes.csv');
});

it('presenta como error cualquier otro fallo', async () => {
  mocks.zip.mockRejectedValue(new ApiError(502, 'SUNAT no respondió'));
  await descargar();
  await waitFor(() =>
    expect(mocks.mostrar).toHaveBeenCalledWith(
      expect.objectContaining({ tono: 'error', detalle: 'SUNAT no respondió' }),
    ),
  );
});
