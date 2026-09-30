import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import type { PagoVoucher, VoucherPeriodo } from '@/types/api';

import { PagoCelda, SeccionPagos, VouchersSinComprobantePanel } from '../Vouchers';

const mocks = vi.hoisted(() => ({ listar: vi.fn(), asociar: vi.fn(), mostrar: vi.fn() }));
vi.mock('@/api/vouchers', () => ({
  listarVouchers: mocks.listar,
  asociarVoucher: mocks.asociar,
}));
vi.mock('@/hooks/useToast', () => ({ useToast: () => ({ mostrar: mocks.mostrar }) }));

const RUC = '20603391692';
const PERIODO = '202609';

const PLIN: VoucherPeriodo = {
  id: 'v1',
  periodo: PERIODO,
  libro: 'ventas',
  fuente: 'plin',
  medio_pago: 'Plin',
  codigo_medio_pago: '003',
  nro_operacion: '5566',
  fecha: '2026-09-30',
  total: '80.00',
  moneda: 'PEN',
  contraparte: 'JUAN PEREZ',
  documento_contraparte: '',
  asociacion: null,
  serie_numero: null,
  periodo_comprobante: null,
  candidatas: [
    {
      periodo: '202608',
      serie_numero: 'B001-45',
      razon_social: 'JUAN PEREZ',
      fecha_emision: '2026-09-30',
      total: '80.00',
      moneda: 'PEN',
    },
  ],
};

function conCliente(hijo: React.ReactNode) {
  return <QueryClientProvider client={new QueryClient()}>{hijo}</QueryClientProvider>;
}

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
  vi.resetAllMocks();
});

it('lista solo los vouchers sin comprobante y los asocia a una candidata', async () => {
  const asociado = { ...PLIN, id: 'v2', nro_operacion: '7777', serie_numero: 'B001-9' };
  mocks.listar.mockResolvedValue([PLIN, asociado]);
  mocks.asociar.mockResolvedValue({ ...PLIN, serie_numero: 'B001-45', asociacion: 'manual' });

  render(
    conCliente(<VouchersSinComprobantePanel ruc={RUC} periodo={PERIODO} libro="ventas" />),
  );

  const tabla = await screen.findByRole('table', { name: 'Vouchers sin comprobante' });
  expect(within(tabla).getByText('5566')).toBeInTheDocument();
  expect(within(tabla).queryByText('7777')).not.toBeInTheDocument();

  await userEvent.click(within(tabla).getByRole('button', { name: 'Asociar' }));
  const dialogo = screen.getByRole('dialog', { name: 'Asociar Plin · Op. 5566' });
  await userEvent.click(
    within(dialogo).getByRole('button', { name: 'Asociar a B001-45 de Agosto 2026' }),
  );

  await waitFor(() =>
    expect(mocks.asociar).toHaveBeenCalledWith(RUC, PERIODO, 'v1', 'B001-45', '202608'),
  );
});

it('asocia a un comprobante escrito a mano', async () => {
  mocks.listar.mockResolvedValue([{ ...PLIN, candidatas: [] }]);
  mocks.asociar.mockResolvedValue({ ...PLIN, serie_numero: 'F001-3' });

  render(
    conCliente(<VouchersSinComprobantePanel ruc={RUC} periodo={PERIODO} libro="ventas" />),
  );
  await userEvent.click(await screen.findByRole('button', { name: 'Asociar' }));

  const dialogo = screen.getByRole('dialog');
  expect(within(dialogo).getByText(/Ningún comprobante de este periodo ni del anterior/)).toBeInTheDocument();
  await userEvent.type(within(dialogo).getByLabelText(/Serie-número/), 'f001-3');
  await userEvent.click(within(dialogo).getByRole('button', { name: 'Asociar' }));

  await waitFor(() =>
    expect(mocks.asociar).toHaveBeenCalledWith(RUC, PERIODO, 'v1', 'F001-3', undefined),
  );
});

it('no se muestra si todos los vouchers tienen comprobante', async () => {
  mocks.listar.mockResolvedValue([{ ...PLIN, serie_numero: 'B001-45' }]);
  const { container } = render(
    conCliente(<VouchersSinComprobantePanel ruc={RUC} periodo={PERIODO} libro="ventas" />),
  );
  await waitFor(() => expect(mocks.listar).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});

it('la celda y la ficha muestran el pago, y la ficha lo desasocia', async () => {
  const pago: PagoVoucher = { ...PLIN, serie_numero: 'B001-45', asociacion: 'auto' };
  mocks.asociar.mockResolvedValue({ ...pago, serie_numero: null });

  render(
    conCliente(
      <>
        <PagoCelda pagos={[pago]} />
        <SeccionPagos ruc={RUC} periodo={PERIODO} pagos={[pago]} />
      </>,
    ),
  );

  expect(screen.getByText('Plin · Op. 5566')).toBeInTheDocument();
  expect(screen.getByText('Automáticamente')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Desasociar' }));
  await waitFor(() =>
    expect(mocks.asociar).toHaveBeenCalledWith(RUC, PERIODO, 'v1', null, undefined),
  );
});
