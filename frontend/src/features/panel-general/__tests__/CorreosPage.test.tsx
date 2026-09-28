import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { ContextoAuthReact } from '@/features/auth/authContext';
import { CorreosPage } from '@/features/panel-general/CorreosPage';
import type { ConfiguracionCorreo, ConfiguracionCorreoUpdate } from '@/types/api';

const mocks = vi.hoisted(() => ({
  obtenerConfiguracionCorreo: vi.fn(),
  guardarConfiguracionCorreo: vi.fn(),
  previsualizarCorreo: vi.fn(),
  enviarCorreoPrueba: vi.fn(),
  obtenerYo: vi.fn(),
  listarEnvios: vi.fn(),
}));

vi.mock('@/api/correos', () => ({
  obtenerConfiguracionCorreo: mocks.obtenerConfiguracionCorreo,
  guardarConfiguracionCorreo: mocks.guardarConfiguracionCorreo,
  previsualizarCorreo: mocks.previsualizarCorreo,
  enviarCorreoPrueba: mocks.enviarCorreoPrueba,
}));
vi.mock('@/api/usuarios', () => ({ obtenerYo: mocks.obtenerYo }));
vi.mock('@/api/solicitudes', () => ({ listarEnvios: mocks.listarEnvios }));

const CONFIG: ConfiguracionCorreo = {
  host: 'smtp.gmail.com',
  puerto: 587,
  seguridad: 'starttls',
  usuario: 'sire@gmail.com',
  password_configurada: true,
  remitente_nombre: 'Sire',
  remitente_correo: '',
  destinatarios_permitidos: ['espinozavaleracinve@gmail.com'],
  max_adjunto_mb: 18,
  dias_enlace: 7,
  url_publica: '',
  plantilla_asunto: 'Asunto propio',
  plantilla_cuerpo: 'Cuerpo propio',
  configurado: true,
  variables: [{ nombre: 'empresas', descripcion: 'Nombres de las empresas' }],
  plantilla_por_defecto: { asunto: 'Sire · {{resumen}}', cuerpo: 'Hola, {{etapas}}' },
};

function primerGuardado(): ConfiguracionCorreoUpdate {
  return mocks.guardarConfiguracionCorreo.mock.calls[0]?.[0] as ConfiguracionCorreoUpdate;
}

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <ToastProvider>
        <ContextoAuthReact.Provider
          value={{
            correo: 'admin@example.com',
            nombre: 'Admin',
            autenticado: true,
            iniciarSesionConGoogle: () => Promise.resolve(),
            salir: () => undefined,
          }}
        >
          <CorreosPage />
        </ContextoAuthReact.Provider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  for (const mock of Object.values(mocks)) mock.mockReset();
  mocks.obtenerYo.mockResolvedValue({ rol: 'admin' });
  mocks.obtenerConfiguracionCorreo.mockResolvedValue(CONFIG);
  mocks.guardarConfiguracionCorreo.mockImplementation((cambios) =>
    Promise.resolve({ ...CONFIG, ...cambios }),
  );
  mocks.listarEnvios.mockResolvedValue([]);
});

describe('configuración del correo', () => {
  it('guarda sin reenviar la contraseña si no se tocó', async () => {
    montar();

    const host = await screen.findByLabelText('Servidor (host)');
    expect(screen.getByText(/Hay una contraseña guardada/)).toBeInTheDocument();
    await userEvent.clear(host);
    await userEvent.type(host, 'smtp.office365.com');
    await userEvent.click(screen.getByRole('button', { name: 'Guardar configuración' }));

    const cambios = primerGuardado();
    expect(cambios.host).toBe('smtp.office365.com');
    expect(cambios.destinatarios_permitidos).toEqual(['espinozavaleracinve@gmail.com']);
    expect(cambios).not.toHaveProperty('password');
    expect(await screen.findByText('Configuración del correo guardada')).toBeInTheDocument();
  });

  it('una contraseña nueva sí se envía', async () => {
    montar();

    await userEvent.type(await screen.findByLabelText('Contraseña'), 'clave-app');
    await userEvent.click(screen.getByRole('button', { name: 'Guardar configuración' }));

    expect(primerGuardado().password).toBe('clave-app');
  });

  it('inserta variables, restaura la plantilla y la previsualiza', async () => {
    mocks.previsualizarCorreo.mockResolvedValue({
      asunto: 'Sire · 2 empresas',
      texto: 'Hola',
      html: '<p>Hola</p>',
    });
    montar();

    const cuerpo = await screen.findByLabelText('Cuerpo');
    await userEvent.click(
      screen.getByRole('button', { name: 'Insertar la variable empresas' }),
    );
    expect(cuerpo).toHaveValue('Cuerpo propio{{empresas}}');

    await userEvent.click(
      screen.getByRole('button', { name: 'Restaurar plantilla por defecto' }),
    );
    expect(cuerpo).toHaveValue('Hola, {{etapas}}');
    expect(screen.getByLabelText('Asunto')).toHaveValue('Sire · {{resumen}}');

    await userEvent.click(screen.getByRole('button', { name: 'Vista previa' }));
    expect(mocks.previsualizarCorreo).toHaveBeenCalledWith(
      'Sire · {{resumen}}',
      'Hola, {{etapas}}',
    );
    expect(await screen.findByTitle('Vista previa del correo')).toHaveAttribute(
      'srcdoc',
      '<p>Hola</p>',
    );
  });

  it('envía la prueba a la sesión y muestra el error del servidor', async () => {
    const { ApiError } = await import('@/lib/http');
    mocks.enviarCorreoPrueba.mockRejectedValue(
      new ApiError(422, 'El servidor de correo rechazó el usuario o la contraseña (SMTP)'),
    );
    montar();

    expect(await screen.findByLabelText('Enviar a')).toHaveValue('admin@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar prueba' }));

    expect(mocks.enviarCorreoPrueba).toHaveBeenCalledWith('admin@example.com');
    expect(await screen.findByText(/rechazó el usuario o la contraseña/)).toBeInTheDocument();
  });

  it('quien no es administrador solo ve los envíos', async () => {
    mocks.obtenerYo.mockResolvedValue({ rol: 'usuario' });
    montar();

    expect(
      await screen.findByText('La configuración del correo es solo para administradores'),
    ).toBeInTheDocument();
    expect(mocks.obtenerConfiguracionCorreo).not.toHaveBeenCalled();
    expect(screen.getByText('Envíos de correo')).toBeInTheDocument();
  });

  it('no tiene violaciones de axe', async () => {
    const { container } = montar();
    await screen.findByLabelText('Servidor (host)');
    expect(
      await axe(container, { rules: { 'color-contrast': { enabled: false } } }),
    ).toHaveNoViolations();
  });
});
