import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { DescargarDetraccionesButton, NpdPanel } from '../Detracciones';

const mocks = vi.hoisted(() => ({
  iniciar: vi.fn(),
  obtener: vi.fn(),
  zip: vi.fn(),
  mostrar: vi.fn(),
  seguir: vi.fn(),
  disponibilidad: vi.fn(),
  listar: vi.fn(),
  individual: vi.fn(),
}));
vi.mock('@/api/detracciones', () => ({
  consultarDetracciones: mocks.iniciar,
  descargarDetracciones: mocks.zip,
  disponibilidadDetracciones: mocks.disponibilidad,
  listarNpds: mocks.listar,
  descargarPdfNpd: mocks.individual,
}));
vi.mock('@/api/jobs', () => ({ obtenerJob: mocks.obtener }));
vi.mock('@/features/jobs/useJobs', () => ({ useJobs: () => ({ seguir: mocks.seguir }) }));
vi.mock('@/hooks/useToast', () => ({ useToast: () => ({ mostrar: mocks.mostrar }) }));

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  vi.resetAllMocks();
  mocks.iniciar.mockResolvedValue({ job_id: 'detraccion-job' });
  mocks.zip.mockResolvedValue(undefined);
  mocks.disponibilidad.mockResolvedValue({ disponible: true });
});

async function descargar() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DescargarDetraccionesButton ruc="20123456789" periodo="202608" />
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Descargar NPD del periodo' })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Descargar NPD del periodo' }));
}

it('consulta las detracciones antes de descargar el ZIP', async () => {
  mocks.obtener.mockResolvedValue({ estado: 'completado', progreso: {} });
  await descargar();
  await waitFor(() => expect(mocks.zip).toHaveBeenCalledWith('20123456789', '202608'));
  expect(mocks.seguir).toHaveBeenCalledWith('detraccion-job');
});

it('deshabilita la descarga mientras consulta y cuando no hay marcas Sí', async () => {
  mocks.disponibilidad.mockResolvedValue({ disponible: false });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DescargarDetraccionesButton ruc="20123456789" periodo="202608" />
    </QueryClientProvider>,
  );
  const boton = screen.getByRole('button', {
    name: 'Descargar NPD del periodo',
  });
  expect(boton).toBeDisabled();
  await waitFor(() =>
    expect(mocks.disponibilidad).toHaveBeenCalledWith('20123456789', '202608'),
  );
  expect(boton).toBeDisabled();
  await userEvent.click(boton);
  expect(mocks.iniciar).not.toHaveBeenCalled();
});

it('no descarga un ZIP anterior si falla la consulta', async () => {
  mocks.obtener.mockResolvedValue({ estado: 'fallido', progreso: {}, error: 'Sesión vencida' });
  await descargar();
  await waitFor(() =>
    expect(mocks.mostrar).toHaveBeenCalledWith(expect.objectContaining({ tono: 'error' })),
  );
  expect(mocks.zip).not.toHaveBeenCalled();
});

it('muestra los NPD del periodo y descarga una fila sin consultar SUNAT', async () => {
  mocks.listar.mockResolvedValue({
    npds: [
      {
        numero: '000123',
        pdf_ruta: 'npd.pdf',
        cabecera: { estado: 'No Vigente', importe: 270 },
        detalle: { concepto: 'Arrendamiento' },
      },
    ],
    consultado_en: '2026-09-07',
  });
  mocks.individual.mockResolvedValue(undefined);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <NpdPanel ruc="20123456789" periodo="202608" />
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByRole('button', { name: '000123' }));
  expect(screen.getByText('Arrendamiento')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
  await userEvent.click(screen.getByRole('button', { name: 'Descargar PDF' }));
  await waitFor(() =>
    expect(mocks.individual).toHaveBeenCalledWith('20123456789', '202608', '000123'),
  );
  expect(mocks.iniciar).not.toHaveBeenCalled();
});
