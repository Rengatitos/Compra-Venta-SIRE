import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { ContextoEmpresasReact } from '@/features/empresas/empresasContext';
import type { ComprobanteExternoResponse } from '@/types/api';

import { ExternosPage } from '../ExternosPage';

const RUC = '20603391692';

const mocks = vi.hoisted(() => ({ listar: vi.fn(), imagen: vi.fn() }));
vi.mock('@/api/comprobantesExternos', () => ({
  POR_PAGINA_EXTERNOS: 100,
  listarComprobantesExternos: mocks.listar,
  descargarImagenExterna: mocks.imagen,
}));

const YAPE: ComprobanteExternoResponse = {
  id: '66f1a2b3c4d5e6f708192a3b',
  ruc: RUC,
  periodo: '202609',
  estado: 'recibido',
  creado_en: '2026-09-19T19:32:11Z',
  id_externo: '01J8ZYAPE',
  libro: 'ventas',
  fuente: 'yape',
  tipo_evidencia: 'voucher',
  tipo_cp: '00',
  tipo_cp_descripcion: 'OTROS',
  serie: '',
  numero: '',
  nro_operacion: '12345678',
  fecha_operacion: '2026-09-19',
  hora_operacion: '14:32',
  moneda: 'PEN',
  total: '150.00',
  base_imponible: null,
  igv: null,
  contraparte: { tipo_doc_identidad: '1', documento: '45678912', nombre: 'JUAN PEREZ' },
  descripcion: 'Pago recibido por Yape',
  confianza: 0.93,
  campos_dudosos: ['total'],
  dispositivo_id: 'web-123',
  enviado_en: '2026-09-19T19:32:10Z',
  tiene_imagen: true,
};

const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

function Envoltura({ children }: { children: ReactNode }) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={cliente}>
        <ToastProvider>
          <ContextoEmpresasReact.Provider
            value={{
              empresas: [],
              ruc: RUC,
              empresaActiva: null,
              cambiarEmpresa: () => undefined,
              recargar: () => undefined,
            }}
          >
            {children}
          </ContextoEmpresasReact.Provider>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  vi.resetAllMocks();
  URL.createObjectURL = vi.fn(() => 'blob:foto');
  URL.revokeObjectURL = vi.fn();
});

describe('ExternosPage', () => {
  it('lista lo que llegó del bot con su fuente y total', async () => {
    mocks.listar.mockResolvedValue({ items: [YAPE], total: 1, periodos: ['202609'] });

    const { container } = render(<ExternosPage />, { wrapper: Envoltura });

    const tabla = await screen.findByRole('table');
    expect(within(tabla).getByRole('button', { name: 'Op. 12345678' })).toBeInTheDocument();
    expect(within(tabla).getByText('Yape')).toBeInTheDocument();
    expect(within(tabla).getByText('JUAN PEREZ')).toBeInTheDocument();
    expect(within(tabla).getByText(/150\.00/)).toBeInTheDocument();
    expect(mocks.listar).toHaveBeenCalledWith(RUC, { libro: 'ventas', periodo: '', pagina: 1 });
    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });

  it('cambiar de libro vuelve a pedir la lista', async () => {
    mocks.listar.mockResolvedValue({ items: [], total: 0, periodos: [] });
    render(<ExternosPage />, { wrapper: Envoltura });

    await userEvent.click(await screen.findByRole('button', { name: 'Compras' }));

    await waitFor(() =>
      expect(mocks.listar).toHaveBeenLastCalledWith(RUC, {
        libro: 'compras',
        periodo: '',
        pagina: 1,
      }),
    );
  });

  it('sin comprobantes explica cómo vincular el bot', async () => {
    mocks.listar.mockResolvedValue({ items: [], total: 0, periodos: [] });

    render(<ExternosPage />, { wrapper: Envoltura });

    expect(await screen.findByText('Aún no llegan ventas desde el bot')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ir a Ajustes' })).toHaveAttribute(
      'href',
      '/ajustes',
    );
  });

  it('el detalle muestra la foto y los datos dudosos', async () => {
    mocks.listar.mockResolvedValue({ items: [YAPE], total: 1, periodos: ['202609'] });
    mocks.imagen.mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));

    render(<ExternosPage />, { wrapper: Envoltura });
    await userEvent.click(await screen.findByRole('button', { name: 'Op. 12345678' }));

    const dialogo = await screen.findByRole('dialog');
    expect(
      await within(dialogo).findByRole('img', { name: /Foto del comprobante/ }),
    ).toHaveAttribute('src', 'blob:foto');
    expect(mocks.imagen).toHaveBeenCalledWith(RUC, YAPE.id, expect.anything());
    expect(
      within(dialogo).getByText('El bot no estaba seguro de algunos datos'),
    ).toBeInTheDocument();
    expect(within(dialogo).getByText('93 %')).toBeInTheDocument();
  });
});
