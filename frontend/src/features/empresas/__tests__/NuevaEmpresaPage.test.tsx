import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { NuevaEmpresaPage } from '@/features/empresas/NuevaEmpresaPage';
import { guardarSesion, limpiarSesion, obtenerSesion } from '@/lib/session';
import type { CargaEmpresas, EmpresaCreada, FilaCarga } from '@/types/api';

const mocks = vi.hoisted(() => ({
  crearEmpresa: vi.fn(),
  cargarEmpresas: vi.fn(),
  obtenerCarga: vi.fn(),
  obtenerCredencialesSunat: vi.fn(),
}));

vi.mock('@/api/empresas', () => ({
  crearEmpresa: mocks.crearEmpresa,
  cargarEmpresas: mocks.cargarEmpresas,
  obtenerCarga: mocks.obtenerCarga,
  obtenerCredencialesSunat: mocks.obtenerCredencialesSunat,
  descargarReporteCarga: vi.fn(),
  descargarPlantillaCarga: vi.fn(),
  listarEmpresas: vi.fn(),
}));

const RUC = '20610202251';

const CREADA: EmpresaCreada = {
  id: '1',
  ruc: RUC,
  nombre: null,
  usuario: 'USUARIO',
  fecha_creacion: null,
  rubro: null,
  carga_id: 'c1',
};

const FILA: FilaCarga = {
  fila: 1,
  ruc: RUC,
  razon_social: 'EMPRESA DE LA FICHA SAC',
  usuario: 'USUARIO',
  estado: 'agregada',
  motivos: ['Registro exitoso'],
  empresa_id: '1',
  fecha_registro: '2026-09-27T10:00:00Z',
};

function carga(parcial: Partial<CargaEmpresas> = {}): CargaEmpresas {
  return {
    id: 'c1',
    modalidad: 'individual',
    archivo: null,
    registrado_por: 'prueba@example.com',
    estado: 'completada',
    progreso: { actual: 1, total: 1, mensaje: 'Registro terminado' },
    filas: [FILA],
    creado_en: '2026-09-27T10:00:00Z',
    terminado_en: '2026-09-27T10:01:00Z',
    ...parcial,
  };
}

const OPCIONES_AXE = { rules: { 'color-contrast': { enabled: false } } } as const;

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

async function llenarFormulario(ruc = RUC) {
  await userEvent.click(screen.getByRole('button', { name: 'Individual' }));
  await userEvent.type(screen.getByLabelText(/RUC/), ruc);
  await userEvent.type(screen.getByLabelText(/Usuario SOL/), 'USUARIO');
  await userEvent.type(screen.getByLabelText(/Contraseña SOL/), 'clave');
}

beforeEach(() => {
  for (const mock of Object.values(mocks)) mock.mockReset();
  mocks.obtenerCredencialesSunat.mockResolvedValue({
    origen: 'existente',
    aplicacion: 'SMARTSIRE',
    client_id: '90a5fdc6…',
    token_valido: true,
    mensaje: 'Se usó la aplicación que la empresa ya tenía en SUNAT.',
  });
  mocks.obtenerCarga.mockResolvedValue(carga());
  guardarSesion({ token: 'jwt', correo: 'prueba@example.com', ruc: '20603391692' });
});

afterEach(() => {
  limpiarSesion();
});

describe('alta de empresa', () => {
  it('abre por defecto en la carga masiva, antes que la individual', () => {
    montar();

    const modos = screen.getAllByRole('button', { name: /^(Carga masiva|Individual)$/ });
    expect(modos.map((boton) => boton.textContent)).toEqual(['Carga masiva', 'Individual']);
    expect(screen.getByRole('button', { name: 'Carga masiva' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByLabelText('Archivo Excel')).toBeInTheDocument();
  });

  it('ofrece volver al panel sin cerrar la sesión', () => {
    montar();

    expect(screen.getByRole('link', { name: 'Volver al panel' })).toHaveAttribute('href', '/');
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).not.toBeInTheDocument();
  });

  it('la razón social es opcional en el alta individual', async () => {
    mocks.crearEmpresa.mockResolvedValue(CREADA);
    montar();

    await llenarFormulario();
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(mocks.crearEmpresa).toHaveBeenCalledWith({
      ruc: RUC,
      usuario: 'USUARIO',
      password: 'clave',
    });
  });

  it('tras crear muestra cómo se completan sus datos y deja entrar en ella', async () => {
    mocks.crearEmpresa.mockResolvedValue(CREADA);
    montar();

    await llenarFormulario();
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(await screen.findByText('EMPRESA DE LA FICHA SAC')).toBeInTheDocument();
    expect(screen.getByText('Agregada')).toBeInTheDocument();
    expect(mocks.obtenerCarga).toHaveBeenCalledWith('c1');

    await userEvent.click(screen.getByRole('button', { name: 'Entrar a la empresa' }));
    expect(await screen.findByText('Panel')).toBeInTheDocument();
    expect(obtenerSesion()?.ruc).toBe(RUC);
  });

  it('rechaza en el navegador un RUC con dígito verificador incorrecto', async () => {
    montar();

    await llenarFormulario('20123456789');
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(await screen.findByText(/RUC inválido/)).toBeInTheDocument();
    expect(mocks.crearEmpresa).not.toHaveBeenCalled();
  });

  it('un RUC ya registrado apunta al selector en vez de dejar al usuario atascado', async () => {
    const { ApiError } = await import('@/lib/http');
    mocks.crearEmpresa.mockRejectedValue(
      new ApiError(409, 'Ya existe una empresa con ese RUC'),
    );
    montar();

    await llenarFormulario();
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'búscalo en el selector de empresas',
    );
  });

  it('sin client_id ni clave, los trae de SUNAT tras crear la empresa', async () => {
    mocks.crearEmpresa.mockResolvedValue(CREADA);
    montar();

    await llenarFormulario();
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(await screen.findByText('EMPRESA DE LA FICHA SAC')).toBeInTheDocument();
    expect(mocks.obtenerCredencialesSunat).toHaveBeenCalledWith(RUC);
    expect(await screen.findByText('Credenciales de API SUNAT: SMARTSIRE')).toBeInTheDocument();
  });

  it('si SUNAT falla, la empresa queda creada y se avisa', async () => {
    const { ApiError } = await import('@/lib/http');
    mocks.crearEmpresa.mockResolvedValue(CREADA);
    mocks.obtenerCredencialesSunat.mockRejectedValue(new ApiError(502, 'SOL no respondió'));
    montar();

    await llenarFormulario();
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(await screen.findByText('EMPRESA DE LA FICHA SAC')).toBeInTheDocument();
    expect(
      await screen.findByText('No se pudieron traer las credenciales de SUNAT'),
    ).toBeInTheDocument();
  });

  it('con client_id y clave tecleados no entra a SOL', async () => {
    mocks.crearEmpresa.mockResolvedValue(CREADA);
    montar();

    await llenarFormulario();
    await userEvent.type(screen.getByLabelText(/Client ID de SUNAT/), 'id-propio');
    await userEvent.type(screen.getByLabelText(/Client Secret de SUNAT/), 'clave-propia');
    await userEvent.click(screen.getByRole('button', { name: 'Registrar empresa' }));

    expect(await screen.findByText('EMPRESA DE LA FICHA SAC')).toBeInTheDocument();
    expect(mocks.obtenerCredencialesSunat).not.toHaveBeenCalled();
  });
});

describe('carga masiva', () => {
  it('sube el Excel y muestra el reporte con estado y motivo por empresa', async () => {
    mocks.cargarEmpresas.mockResolvedValue({ carga_id: 'c2' });
    mocks.obtenerCarga.mockResolvedValue(
      carga({
        id: 'c2',
        modalidad: 'masiva',
        progreso: { actual: 2, total: 2, mensaje: 'Registro terminado' },
        filas: [
          {
            fila: 2,
            ruc: RUC,
            razon_social: 'EMPRESA A',
            usuario: 'USU_A',
            estado: 'agregada_con_observaciones',
            motivos: ['Error al obtener el CIIU: la ficha RUC no trae actividades'],
            empresa_id: '1',
            fecha_registro: null,
          },
          {
            fila: 3,
            ruc: '20123456789',
            razon_social: 'EMPRESA B',
            usuario: 'USU_B',
            estado: 'no_agregada',
            motivos: ['RUC inválido'],
            empresa_id: null,
            fecha_registro: null,
          },
        ],
      }),
    );
    montar();

    const archivo = new File(['x'], 'empresas.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    await userEvent.upload(screen.getByLabelText('Archivo Excel'), archivo);

    expect(mocks.cargarEmpresas).toHaveBeenCalledWith(archivo);
    expect(await screen.findByText('Agregada con observaciones')).toBeInTheDocument();
    expect(screen.getByText('RUC inválido')).toBeInTheDocument();
    expect(
      screen.getByText(/0 agregadas · 1 con observaciones · 1 no agregadas/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Descargar reporte' })).toBeInTheDocument();
  });

  it('muestra el avance mientras la carga sigue en curso', async () => {
    mocks.cargarEmpresas.mockResolvedValue({ carga_id: 'c3' });
    mocks.obtenerCarga.mockResolvedValue(
      carga({
        estado: 'en_progreso',
        progreso: { actual: 0, total: 1, mensaje: '0 de 1 filas' },
        filas: [
          {
            ...FILA,
            estado: 'pendiente',
            motivos: ['Completando los datos de SUNAT'],
          },
        ],
      }),
    );
    montar();

    await userEvent.upload(
      screen.getByLabelText('Archivo Excel'),
      new File(['x'], 'empresas.xlsx'),
    );

    expect(await screen.findByText(/Puedes cerrar esta página/)).toBeInTheDocument();
    expect(screen.getByText('En proceso')).toBeInTheDocument();
  });

  it('rechaza lo que no es Excel sin subirlo', async () => {
    montar();

    await userEvent.upload(
      screen.getByLabelText('Archivo Excel'),
      new File(['a,b'], 'empresas.csv', { type: 'text/csv' }),
      { applyAccept: false },
    );

    expect(await screen.findByText(/Solo se permiten archivos Excel/)).toBeInTheDocument();
    expect(mocks.cargarEmpresas).not.toHaveBeenCalled();
  });

  it('no tiene violaciones de axe', async () => {
    const { container } = montar();
    expect(await axe(container, OPCIONES_AXE)).toHaveNoViolations();
  });
});
