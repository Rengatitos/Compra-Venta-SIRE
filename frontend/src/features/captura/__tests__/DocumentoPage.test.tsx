import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { accionDocumento, editarDocumento, obtenerDocumento } from '@/api/captura';
import type { Documento } from '@/api/captura';
import { DocumentoPage } from '../DocumentoPage';

vi.mock('@/features/auth/useAuth', () => ({ useRuc: () => '20000000001' }));
vi.mock('@/api/captura', () => ({
  obtenerDocumento: vi.fn(),
  archivoDocumento: vi.fn(() => new Promise<Blob>(() => undefined)),
  editarDocumento: vi.fn(),
  accionDocumento: vi.fn(),
  confirmarCoincidencia: vi.fn(),
}));

function documentFixture(id: string, total: string): Documento {
  return {
    id, revision: 1, status: 'READY', document_type: 'FACTURA',
    document_date: '2026-09-01', received_at: '2026-09-22T10:00:00Z',
    accounting_period: '202609', period_validation: 'MATCH', source: 'WEB', batch_id: null,
    issues: [], extracted: { fields: {
      'amounts.total': { value: total, status: 'EXTRACTED', confidence: 1, source: 'OCR' },
      'document.issue_date': { value: '2026-09-01', status: 'EXTRACTED', confidence: 1, source: 'OCR' },
      'payment.bank': { value: 'BCP', status: 'EXTRACTED', confidence: 1, source: 'OCR' },
    } },
  };
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/comprobantes/a']}>
        <Routes><Route path="/comprobantes/:id" element={<DocumentoPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Revisión documental', () => {
  beforeEach(() => vi.clearAllMocks());

  it('descarta el borrador anterior al navegar a un documento con igual revisión', async () => {
    const first = documentFixture('a', '118.00');
    first.matches = [{ id: 'match', documents: ['a', 'b'], score: 90, status: 'SUGGESTED' }];
    const second = { ...documentFixture('b', '99.00'), document_type: 'BANK_TRANSFER' };
    vi.mocked(obtenerDocumento).mockImplementation((id) => Promise.resolve(id === 'a' ? first : second));
    setup();
    expect(await screen.findByLabelText('Total')).toHaveValue('118.00');
    fireEvent.change(screen.getByLabelText('Total'), { target: { value: '555' } });
    fireEvent.click(screen.getByRole('link', { name: 'Ver documento relacionado' }));
    await waitFor(() => expect(screen.getByLabelText('Total')).toHaveValue('99.00'));
    expect(screen.getByLabelText('Tipo de documento')).toHaveValue('BANK_TRANSFER');
    expect(screen.getByRole('button', { name: 'Guardar correcciones' })).toBeDisabled();
  });

  it('requiere guardar cambios antes de confirmar y usa la revisión actualizada', async () => {
    const doc = documentFixture('a', '118.00');
    const corrected = documentFixture('a', '236.00');
    corrected.revision = 2;
    vi.mocked(obtenerDocumento).mockResolvedValue(doc);
    vi.mocked(editarDocumento).mockImplementation(() => {
      vi.mocked(obtenerDocumento).mockResolvedValue(corrected);
      return Promise.resolve(corrected);
    });
    vi.mocked(accionDocumento).mockResolvedValue({ ...corrected, status: 'CONFIRMED', revision: 3 });
    setup();
    await screen.findByLabelText('Total');
    fireEvent.change(screen.getByLabelText('Total'), { target: { value: '236.00' } });
    expect(screen.getByRole('button', { name: 'Confirmar', exact: true })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar correcciones' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar', exact: true })).toBeEnabled());
    expect(editarDocumento).toHaveBeenCalledWith(doc, { 'amounts.total': '236.00' }, 'FACTURA');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar', exact: true }));
    await waitFor(() => expect(accionDocumento).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'a', revision: 2 }), 'confirm', expect.anything(),
    ));
  });

  it('muestra pago vinculado y bloquea correcciones conservando la confirmación', async () => {
    const doc = documentFixture('a', '118.00');
    doc.associated_payment = { document_id: 'pago', channel: 'YAPE', method: null, operation_number: 'OP-99' };
    vi.mocked(obtenerDocumento).mockResolvedValue(doc);
    setup();
    expect(await screen.findByRole('link', { name: 'Ver pago vinculado' })).toHaveAttribute('href', '/comprobantes/pago');
    expect(screen.getByText(/Pago vinculado: YAPE/)).toHaveTextContent('OP-99');
    expect(screen.getByLabelText('Total')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reprocesar OCR' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Confirmar', exact: true })).toBeEnabled();
  });

  it('permite corregir campos adicionales y no permite periodos con mes inválido', async () => {
    vi.mocked(obtenerDocumento).mockResolvedValue(documentFixture('a', '118.00'));
    setup();
    await screen.findByLabelText('Total');
    fireEvent.click(screen.getByText('Corregir otros campos extraídos'));
    expect(screen.getByLabelText('Banco')).toHaveValue('BCP');
    fireEvent.change(screen.getByLabelText('Periodo contable (YYYYMM)'), { target: { value: '202613' } });
    expect(screen.getByRole('button', { name: 'Asignar este periodo' })).toBeDisabled();
  });
});
