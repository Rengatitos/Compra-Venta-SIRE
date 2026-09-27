import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { EnviosCorreo } from '@/features/panel-general/EnviosCorreo';
import { SolicitudesPanel } from '@/features/panel-general/SolicitudesPanel';
import type { EnvioListado, SolicitudResponse } from '@/types/api';

const mocks = vi.hoisted(() => ({
  listarSolicitudes: vi.fn(),
  obtenerSolicitud: vi.fn(),
  reintentarSolicitud: vi.fn(),
  descargarZipSolicitud: vi.fn(),
  listarEnvios: vi.fn(),
}));

vi.mock('@/api/solicitudes', () => mocks);

function solicitud(parcial: Partial<SolicitudResponse> = {}): SolicitudResponse {
  return {
    id: 's1',
    creado_por: 'contador@example.com',
    creado_en: '2026-09-27T15:00:00Z',
    terminado_en: '2026-09-27T16:00:00Z',
    estado: 'completada_con_errores',
    clasificar: true,
    error: null,
    progreso: { actual: 1, total: 1 },
    items: [
      {
        ruc: '20610202251',
        nombre: 'Alfa SAC',
        periodo: '202608',
        estado: 'con_errores',
        observaciones: [],
        pasos: [
          { paso: 'sire_compras', estado: 'completado', job_id: 'a', nota: null },
          {
            paso: 'detalle_compras',
            estado: 'encolado',
            job_id: 'b',
            nota: null,
            job_estado: 'pendiente',
            intentos: 2,
            max_intentos: 5,
            siguiente_intento_en: null,
          },
          {
            paso: 'clasificacion_compras',
            estado: 'fallido',
            job_id: 'c',
            nota: null,
            error: 'GEMINI_API_ERROR: 503',
          },
        ],
      },
    ],
    zip: { archivo: 'DESCARGA_2026-09-27.zip', bytes: 1024, generado_en: null },
    envios: [
      {
        correo: 'contador@example.com',
        empresas: [{ ruc: '20610202251', nombre: 'Alfa SAC' }],
        periodos: ['202608'],
        estado: 'enviado',
        modo: 'adjunto',
        intentos: 1,
        error: null,
        creado_en: null,
        enviado_en: '2026-09-27T16:00:00Z',
      },
    ],
    ...parcial,
  };
}

function montar(ui = <SolicitudesPanel />) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  for (const mock of Object.values(mocks)) mock.mockReset();
  mocks.listarSolicitudes.mockResolvedValue([solicitud()]);
  mocks.obtenerSolicitud.mockResolvedValue(solicitud());
  mocks.reintentarSolicitud.mockResolvedValue(solicitud({ estado: 'en_progreso' }));
});

describe('solicitudes de procesamiento masivo', () => {
  it('lista cada solicitud con su estado y avance', async () => {
    montar();
    const tabla = await screen.findByRole('group', {
      name: 'Solicitudes de procesamiento masivo',
    });
    expect(within(tabla).getByText('Completada con errores')).toBeInTheDocument();
    expect(within(tabla).getByText('1 de 1 terminados')).toBeInTheDocument();
  });

  it('el detalle muestra cada paso, sus reintentos y los correos', async () => {
    montar();
    await userEvent.click(await screen.findByRole('button', { name: 'Ver detalle' }));

    const avance = await screen.findByRole('group', { name: 'Avance por empresa y periodo' });
    expect(within(avance).getByText('Reintento 3 de 5')).toBeInTheDocument();
    expect(within(avance).getByText('GEMINI_API_ERROR: 503')).toBeInTheDocument();
    const correos = screen.getByRole('group', { name: 'Correos' });
    expect(within(correos).getByText('ZIP adjunto')).toBeInTheDocument();
  });

  it('descarga el ZIP y reintenta lo fallido', async () => {
    montar();
    await userEvent.click(await screen.findByRole('button', { name: 'Descargar ZIP' }));
    expect(mocks.descargarZipSolicitud).toHaveBeenCalledWith('s1');

    await userEvent.click(screen.getByRole('button', { name: 'Reintentar fallidos' }));
    expect(mocks.reintentarSolicitud).toHaveBeenCalledWith('s1');
  });

  it('una solicitud en curso no ofrece reintentar ni ZIP', async () => {
    mocks.listarSolicitudes.mockResolvedValue([
      solicitud({ estado: 'en_progreso', zip: null }),
    ]);
    montar();
    await screen.findByText('En proceso');
    expect(
      screen.queryByRole('button', { name: 'Reintentar fallidos' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Descargar ZIP' })).not.toBeInTheDocument();
  });

  it('no tiene violaciones de axe', async () => {
    const { container } = montar();
    await screen.findByText('Completada con errores');
    expect(
      await axe(container, { rules: { 'color-contrast': { enabled: false } } }),
    ).toHaveNoViolations();
  });
});

describe('envíos de correo', () => {
  it('muestra correo, empresas, periodos, fecha y estado del envío', async () => {
    const envio: EnvioListado = {
      ...solicitud().envios[0]!,
      correo: 'cliente@alfa.pe',
      estado: 'bloqueado',
      error: 'Destinatario fuera de CORREO_DESTINATARIOS_PERMITIDOS en este entorno',
      solicitud_id: 's1',
      solicitud_creada_en: '2026-09-27T15:00:00Z',
    };
    mocks.listarEnvios.mockResolvedValue([envio]);
    montar(<EnviosCorreo />);

    const tabla = await screen.findByRole('group', { name: 'Envíos de correo' });
    expect(within(tabla).getByText('cliente@alfa.pe')).toBeInTheDocument();
    expect(within(tabla).getByText('Alfa SAC')).toBeInTheDocument();
    expect(within(tabla).getByText('No permitido en este entorno')).toBeInTheDocument();
  });
});
