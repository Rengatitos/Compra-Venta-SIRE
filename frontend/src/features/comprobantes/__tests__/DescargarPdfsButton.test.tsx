import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { DescargarPdfsButton } from '../DescargarPdfsButton';

const mocks = vi.hoisted(() => ({
  iniciar: vi.fn(),
  obtener: vi.fn(),
  zip: vi.fn(),
  mostrar: vi.fn(),
  seguir: vi.fn(),
}));
vi.mock('@/api/pdfs', () => ({
  iniciarDescargaPdfs: mocks.iniciar,
  descargarZipPdfs: mocks.zip,
}));
vi.mock('@/api/jobs', () => ({ obtenerJob: mocks.obtener }));
vi.mock('@/features/jobs/useJobs', () => ({ useJobs: () => ({ seguir: mocks.seguir }) }));
vi.mock('@/hooks/useToast', () => ({ useToast: () => ({ mostrar: mocks.mostrar }) }));

beforeEach(() => {
  vi.resetAllMocks();
  mocks.iniciar.mockResolvedValue({ job_id: 'pdf-job' });
  mocks.zip.mockResolvedValue(undefined);
});

async function descargar() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DescargarPdfsButton ruc="20123456789" periodo="202608" libro="ventas" />
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole('button', { name: /Descargar comprobantes SUNAT/ }));
}

it('obtiene los PDFs del periodo y libro antes de descargar el ZIP', async () => {
  mocks.obtener.mockResolvedValue({
    estado: 'completado',
    progreso: {},
    resultado: { sin_pdf: 0, pendientes: 0 },
  });
  await descargar();
  await waitFor(() =>
    expect(mocks.zip).toHaveBeenCalledWith('20123456789', '202608', 'ventas'),
  );
  expect(mocks.iniciar).toHaveBeenCalledWith('20123456789', '202608', 'ventas');
  expect(mocks.seguir).toHaveBeenCalledWith('pdf-job');
});

it('avisa de los faltantes sin presentar el ZIP como completo', async () => {
  mocks.obtener.mockResolvedValue({
    estado: 'completado',
    progreso: {},
    resultado: { sin_pdf: 2 },
  });
  await descargar();
  await waitFor(() =>
    expect(mocks.mostrar).toHaveBeenCalledWith(
      expect.objectContaining({ titulo: 'ZIP descargado con PDFs pendientes' }),
    ),
  );
});

it('no descarga el ZIP cuando falla SUNAT', async () => {
  mocks.obtener.mockResolvedValue({ estado: 'fallido', progreso: {}, error: 'Sesión vencida' });
  await descargar();
  await waitFor(() =>
    expect(mocks.mostrar).toHaveBeenCalledWith(
      expect.objectContaining({ tono: 'error', detalle: 'Sesión vencida' }),
    ),
  );
  expect(mocks.zip).not.toHaveBeenCalled();
});
