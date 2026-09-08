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
  descargarZipPdfs: mocks.zip,
}));
vi.mock('@/hooks/useToast', () => ({ useToast: () => ({ mostrar: mocks.mostrar }) }));

beforeEach(() => {
  vi.resetAllMocks();
  mocks.zip.mockResolvedValue(undefined);
});

async function descargar() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DescargarPdfsButton ruc="20123456789" periodo="202608" libro="ventas" />
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole('button', { name: /ZIP de PDFs SUNAT/ }));
}

it('descarga el ZIP del periodo y libro sin entrar al portal SOL', async () => {
  // La descarga de PDFs desde SUNAT vive en «Completar con GLOSA»: este botón
  // sólo empaqueta lo que ya está en disco.
  await descargar();
  await waitFor(() =>
    expect(mocks.zip).toHaveBeenCalledWith('20123456789', '202608', 'ventas'),
  );
  expect(mocks.mostrar).not.toHaveBeenCalled();
});

it('explica qué hacer cuando todavía no hay PDFs', async () => {
  mocks.zip.mockRejectedValue(new ApiError(404, 'No hay PDFs guardados'));
  await descargar();
  await waitFor(() =>
    expect(mocks.mostrar).toHaveBeenCalledWith(
      expect.objectContaining({ tono: 'neutro', titulo: 'Todavía no hay PDFs guardados' }),
    ),
  );
  const aviso = mocks.mostrar.mock.calls[0]?.[0] as { detalle?: string } | undefined;
  expect(aviso?.detalle).toContain('Completar con GLOSA');
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
