import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { conciliarPeriodo, listarDocumentos, obtenerLote, resumenPeriodoCaptura } from '@/api/captura';
import { InventarioPage } from '../InventarioPage';

vi.mock('@/features/auth/useAuth', () => ({ useRuc: () => '20000000001' }));
vi.mock('@/api/captura', () => ({
  listarDocumentos: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1 }),
  listarPeriodosCaptura: vi.fn().mockResolvedValue([{ _id: '202609', count: 2 }]),
  resumenPeriodoCaptura: vi.fn().mockResolvedValue([]),
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
        <Routes>
          <Route path="/comprobantes" element={<InventarioPage />} />
          <Route path="/lotes/:id" element={<InventarioPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Inventario documental', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listarDocumentos).mockResolvedValue({ items: [], total: 0, page: 1 });
    vi.mocked(resumenPeriodoCaptura).mockResolvedValue([]);
  });
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

  it('reinicia la paginación al ordenar y conserva los filtros guardados en la URL', async () => {
    setup('/comprobantes?periodo=202609&pagina=3&tipo=BANK_TRANSFER&q=banco');
    await waitFor(() => expect(listarDocumentos).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 3, period: '202609', type: 'BANK_TRANSFER', q: 'banco' }),
    ));
    fireEvent.change(screen.getByLabelText('Ordenar por'), { target: { value: 'document_date' } });
    await waitFor(() => expect(listarDocumentos).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, sort: 'document_date', type: 'BANK_TRANSFER', q: 'banco' }),
    ));
  });

  it('muestra qué estados incluye Solo observados y elimina el estado incompatible', async () => {
    setup('/comprobantes?estado=CONFIRMED&pagina=2');
    fireEvent.click(screen.getByLabelText('Solo observados'));
    await waitFor(() => expect(listarDocumentos).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, status: '', observed: true }),
    ));
    expect(screen.getByLabelText('Estado')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Solo observados'));
    expect(screen.getByLabelText('Estado')).toHaveValue('');
    expect(screen.getByLabelText('Estado')).toBeEnabled();
  });

  it('muestra canal y operación del pago conciliado en la fila del comprobante', async () => {
    vi.mocked(listarDocumentos).mockResolvedValue({
      items: [{
        id: 'factura', revision: 1, status: 'CONFIRMED', document_date: '2026-09-01',
        received_at: '2026-09-22T10:00:00Z', accounting_period: '202609',
        period_validation: 'MATCH', source: 'WEB', batch_id: null, issues: [],
        associated_payment: { document_id: 'pago', channel: 'YAPE', method: null, operation_number: 'OP-9823' },
      }], total: 1, page: 1,
    });
    setup('/comprobantes');
    expect(await screen.findByRole('cell', { name: 'YAPE' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'OP-9823' })).toBeInTheDocument();
  });

  it('consulta el resumen del periodo y desglosa documentos por estado y tipo', async () => {
    vi.mocked(resumenPeriodoCaptura).mockResolvedValue([
      { _id: { type: 'FACTURA', status: 'READY' }, count: 3 },
      { _id: { type: 'FACTURA', status: 'CONFIRMED' }, count: 2 },
      { _id: { type: 'BANK_TRANSFER', status: 'NEEDS_REVIEW' }, count: 1 },
    ]);
    const { container } = setup('/comprobantes?periodo=202609');
    expect(await screen.findByText('Factura: 5')).toBeInTheDocument();
    expect(resumenPeriodoCaptura).toHaveBeenCalledWith('202609');
    expect(screen.getByText('Total recibidos').parentElement).toHaveTextContent('6');
    expect(screen.getByText('Listos para confirmar').parentElement).toHaveTextContent('3');
    expect(screen.getByText('Observados').parentElement).toHaveTextContent('1');
    expect(screen.getByText('Confirmados').parentElement).toHaveTextContent('2');
    expect(await axe(container, { rules: { 'color-contrast': { enabled: false } } })).toHaveNoViolations();
  });

  it('usa el periodo del lote para conciliación sin exigir otro filtro de periodo', async () => {
    vi.mocked(obtenerLote).mockResolvedValue({ id: 'lote', accounting_period: '202608', status: 'READY_FOR_REVIEW', received_count: 2, created_at: '2026-09-22' });
    vi.mocked(conciliarPeriodo).mockResolvedValue({ suggested: 1 });
    setup('/lotes/lote');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Buscar medios de pago' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Buscar medios de pago' }));
    await waitFor(() => expect(conciliarPeriodo).toHaveBeenCalledWith('202608'));
    expect(resumenPeriodoCaptura).toHaveBeenCalledWith('202608');
  });
});
