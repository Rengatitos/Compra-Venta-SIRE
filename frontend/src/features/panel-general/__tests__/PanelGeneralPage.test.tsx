import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { ContextoAuthReact } from '@/features/auth/authContext';
import { PanelGeneralPage } from '@/features/panel-general/PanelGeneralPage';
import { guardarSesion, limpiarSesion, obtenerSesion } from '@/lib/session';
import type { JobResponse, ResumenEmpresa, ResumenEmpresas } from '@/types/api';

const mocks = vi.hoisted(() => ({
  obtenerResumenEmpresas: vi.fn(),
  listarJobs: vi.fn(),
  crearSolicitud: vi.fn(),
  listarSolicitudes: vi.fn(),
  listarEnvios: vi.fn(),
}));

vi.mock('@/api/empresas', () => ({ obtenerResumenEmpresas: mocks.obtenerResumenEmpresas }));
vi.mock('@/api/jobs', () => ({ listarJobs: mocks.listarJobs, reintentarJob: vi.fn() }));
vi.mock('@/api/usuarios', () => ({ obtenerYo: vi.fn().mockResolvedValue({ rol: 'admin' }) }));
vi.mock('@/api/solicitudes', () => ({
  crearSolicitud: mocks.crearSolicitud,
  listarSolicitudes: mocks.listarSolicitudes,
  obtenerSolicitud: vi.fn(),
  reintentarSolicitud: vi.fn(),
  descargarZipSolicitud: vi.fn(),
  listarEnvios: mocks.listarEnvios,
}));

function job(parcial: Partial<JobResponse> = {}): JobResponse {
  return {
    job_id: 'j1',
    tipo: 'sincronizacion_sire',
    estado: 'completado',
    ruc: '20610202251',
    periodo: '202608',
    libro: 'compras',
    progreso: {
      actual: 1,
      total: 1,
      mensaje: 'Se sincronizaron 40 comprobantes',
      porcentaje: 100,
    },
    resultado: null,
    error: null,
    creado_en: '2026-09-27T10:00:00Z',
    actualizado_en: '2026-09-27T10:01:00Z',
    ...parcial,
  };
}

function empresa(parcial: Partial<ResumenEmpresa> = {}): ResumenEmpresa {
  return {
    ruc: '20610202251',
    nombre: 'Alfa SAC',
    correos_notificacion: ['conta@alfa.pe'],
    total_periodos: 2,
    periodos: [
      { periodo: '202608', estado: 'sincronizado' },
      { periodo: '202607', estado: 'pendiente' },
    ],
    ultima_actualizacion_sire: '2026-09-27T10:01:00Z',
    ultimo_proceso: job(),
    procesos_por_estado: { pendiente: 0, en_progreso: 0, completado: 3, fallido: 1 },
    ...parcial,
  };
}

const RESUMEN: ResumenEmpresas = {
  total_empresas: 2,
  dias: 30,
  procesos_por_estado: { pendiente: 1, en_progreso: 2, completado: 3, fallido: 1 },
  empresas: [
    empresa(),
    empresa({
      ruc: '20603391692',
      nombre: 'Beta EIRL',
      correos_notificacion: [],
      total_periodos: 0,
      periodos: [],
      ultima_actualizacion_sire: null,
      ultimo_proceso: null,
    }),
  ],
};

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={['/empresas']}>
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
              <Route path="/empresas" element={<PanelGeneralPage />} />
              <Route path="/" element={<p>Panel de la empresa</p>} />
              <Route path="/ajustes" element={<p>Ajustes</p>} />
            </Routes>
          </ContextoAuthReact.Provider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  for (const mock of Object.values(mocks)) mock.mockReset();
  mocks.obtenerResumenEmpresas.mockResolvedValue(RESUMEN);
  mocks.listarJobs.mockResolvedValue([job()]);
  mocks.listarSolicitudes.mockResolvedValue([]);
  mocks.listarEnvios.mockResolvedValue([]);
  guardarSesion({ token: 'jwt', correo: 'prueba@example.com', ruc: null });
});

afterEach(() => {
  limpiarSesion();
});

describe('panel general de empresas', () => {
  it('muestra los totales de empresas y de procesos por estado', async () => {
    montar();

    const empresas = await screen.findByText('Empresas registradas');
    expect(empresas.parentElement).toHaveTextContent('2');
    expect(screen.getByText('En ejecución').parentElement).toHaveTextContent('2');
    expect(screen.getByText('Con errores').parentElement).toHaveTextContent('1');
  });

  it('lista cada empresa con sus periodos, su última descarga SIRE y sus correos', async () => {
    montar();

    const tabla = await screen.findByRole('group', { name: 'Listado de empresas' });
    const alfa = within(tabla).getByText('Alfa SAC').closest('tr');
    const beta = within(tabla).getByText('Beta EIRL').closest('tr');
    expect(alfa).toHaveTextContent('conta@alfa.pe');
    expect(alfa).toHaveTextContent('sincronizado');
    expect(beta).toHaveTextContent('Nunca');
    expect(beta).toHaveTextContent('Sin correos');
    expect(beta).toHaveTextContent('Sin periodos');
  });

  it('filtra por RUC o nombre', async () => {
    montar();
    const tabla = await screen.findByRole('group', { name: 'Listado de empresas' });

    await userEvent.type(screen.getByLabelText('Filtrar por RUC o nombre'), 'beta');

    expect(within(tabla).queryByText('Alfa SAC')).not.toBeInTheDocument();
    expect(within(tabla).getByText('Beta EIRL')).toBeInTheDocument();
  });

  it('«Entrar» deja la empresa activa y abre su panel', async () => {
    montar();

    await userEvent.click(
      await screen.findByRole('button', { name: 'Entrar al panel de Beta EIRL' }),
    );

    expect(await screen.findByText('Panel de la empresa')).toBeInTheDocument();
    expect(obtenerSesion()?.ruc).toBe('20603391692');
  });

  it('«Editar» los correos lleva a los ajustes de esa empresa', async () => {
    montar();

    await userEvent.click(
      await screen.findByRole('button', { name: 'Editar los correos de Alfa SAC' }),
    );

    expect(await screen.findByText('Ajustes')).toBeInTheDocument();
    expect(obtenerSesion()?.ruc).toBe('20610202251');
  });

  it('el historial muestra los procesos de todas las empresas', async () => {
    montar();

    const historial = await screen.findByRole('group', {
      name: 'Historial de procesos de todas las empresas',
    });
    expect(within(historial).getByText('Descarga SIRE')).toBeInTheDocument();
    expect(mocks.listarJobs).toHaveBeenCalledWith(null, expect.objectContaining({ limit: 25 }));
  });

  it('procesa las empresas marcadas en el rango de meses elegido', async () => {
    mocks.crearSolicitud.mockResolvedValue({ progreso: { actual: 0, total: 2 } });
    montar();

    await userEvent.click(await screen.findByRole('checkbox', { name: 'Procesar Alfa SAC' }));
    const desde = screen.getByLabelText('Desde');
    await userEvent.clear(desde);
    await userEvent.type(desde, '2026-07');
    const hasta = screen.getByLabelText('Hasta');
    await userEvent.clear(hasta);
    await userEvent.type(hasta, '2026-08');
    await userEvent.click(screen.getByRole('button', { name: 'Procesar' }));

    expect(mocks.crearSolicitud).toHaveBeenCalledWith({
      empresas: ['20610202251'],
      periodos: ['202607', '202608'],
      clasificar: true,
    });
    expect(await screen.findByText('Procesamiento en cola')).toBeInTheDocument();
    // La selección se limpia tras lanzar.
    expect(screen.getByRole('checkbox', { name: 'Procesar Alfa SAC' })).not.toBeChecked();
  });

  it('con todas marcadas pide «todas» y todos sus periodos registrados', async () => {
    mocks.crearSolicitud.mockResolvedValue({ progreso: { actual: 0, total: 3 } });
    montar();

    await userEvent.click(await screen.findByRole('checkbox', { name: 'Seleccionar todas' }));
    await userEvent.click(
      screen.getByRole('radio', { name: 'Todos los periodos registrados de cada empresa' }),
    );
    await userEvent.click(screen.getByRole('checkbox', { name: /Clasificar con IA/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Procesar' }));

    expect(mocks.crearSolicitud).toHaveBeenCalledWith({
      empresas: 'todas',
      periodos: 'todos',
      clasificar: false,
    });
  });

  it('sin empresas marcadas no deja procesar', async () => {
    montar();
    expect(await screen.findByRole('button', { name: 'Procesar' })).toBeDisabled();
  });

  it('no tiene violaciones de axe', async () => {
    const { container } = montar();
    await screen.findByRole('group', { name: 'Listado de empresas' });
    expect(
      await axe(container, { rules: { 'color-contrast': { enabled: false } } }),
    ).toHaveNoViolations();
  });
});
