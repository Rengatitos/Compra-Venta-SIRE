import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { listarDocumentos } from '@/api/captura';
import { InventarioPage } from '../InventarioPage';

vi.mock('@/features/auth/useAuth', () => ({ useRuc: () => '20000000001' }));
vi.mock('@/api/captura', () => ({
  listarDocumentos: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1 }),
  listarPeriodosCaptura: vi.fn().mockResolvedValue([{ _id: '202609', count: 2 }]),
  obtenerLote: vi.fn(),
  accionLote: vi.fn(),
  cargarDocumento: vi.fn(),
  conciliarPeriodo: vi.fn(),
  crearLote: vi.fn(),
  exportarInventario: vi.fn(),
}));

function setup(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <InventarioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Inventario documental', () => {
  it('filtra por periodo contable y no por fecha de recepción', async () => {
    setup('/comprobantes?periodo=202609');
    await waitFor(() =>
      expect(listarDocumentos).toHaveBeenCalledWith(
        expect.objectContaining({ period: '202609' }),
      ),
    );
    fireEvent.change(screen.getByLabelText('Periodo contable'), {
      target: { value: '2026-10' },
    });
    await waitFor(() =>
      expect(listarDocumentos).toHaveBeenCalledWith(
        expect.objectContaining({ period: '202610' }),
      ),
    );
  });

  it('mantiene el filtro de observados al cambiar de periodo', async () => {
    setup('/comprobantes?observados=true');
    fireEvent.change(screen.getByLabelText('Periodo contable'), {
      target: { value: '2026-09' },
    });
    await waitFor(() =>
      expect(listarDocumentos).toHaveBeenCalledWith(
        expect.objectContaining({ period: '202609', observed: true }),
      ),
    );
    expect(screen.getByLabelText('Solo observados')).toBeChecked();
  });
});
