import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ToastProvider } from '@/components/ui/ToastProvider';
import { CorreosEmpresaPanel } from '@/features/empresa/CorreosEmpresaPanel';
import type { EmpresaResponse } from '@/types/api';

const mocks = vi.hoisted(() => ({ guardarCorreos: vi.fn() }));

vi.mock('@/api/empresas', () => ({ guardarCorreos: mocks.guardarCorreos }));

const RUC = '20610202251';

function empresa(correos: string[]): EmpresaResponse {
  return {
    id: '1',
    ruc: RUC,
    nombre: 'Alfa',
    usuario: 'U',
    fecha_creacion: null,
    rubro: null,
    correos_notificacion: correos,
  };
}

function montar(correos: string[] = []) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <ToastProvider>
        <CorreosEmpresaPanel ruc={RUC} empresa={empresa(correos)} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe('correos para envío de resultados', () => {
  beforeEach(() => {
    mocks.guardarCorreos.mockReset();
    mocks.guardarCorreos.mockResolvedValue(empresa([]));
  });

  it('agrega un correo normalizado y guarda la lista completa', async () => {
    montar(['a@b.pe']);

    await userEvent.type(screen.getByLabelText('Nuevo correo'), ' Conta@Empresa.PE ');
    await userEvent.click(screen.getByRole('button', { name: 'Agregar' }));
    await userEvent.click(screen.getByRole('button', { name: 'Guardar correos' }));

    expect(mocks.guardarCorreos).toHaveBeenCalledWith(RUC, ['a@b.pe', 'conta@empresa.pe']);
  });

  it('rechaza lo que no es un correo y los duplicados', async () => {
    montar(['a@b.pe']);

    await userEvent.type(screen.getByLabelText('Nuevo correo'), 'no-es-correo');
    await userEvent.click(screen.getByRole('button', { name: 'Agregar' }));
    expect(screen.getByText(/Escribe un correo válido/)).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText('Nuevo correo'));
    await userEvent.type(screen.getByLabelText('Nuevo correo'), 'A@B.pe');
    await userEvent.click(screen.getByRole('button', { name: 'Agregar' }));
    expect(screen.getByText('Ese correo ya está en la lista.')).toBeInTheDocument();
  });

  it('quitar el último correo guarda una lista vacía', async () => {
    montar(['a@b.pe']);

    await userEvent.click(screen.getByRole('button', { name: 'Quitar a@b.pe' }));
    await userEvent.click(screen.getByRole('button', { name: 'Guardar correos' }));

    expect(mocks.guardarCorreos).toHaveBeenCalledWith(RUC, []);
  });

  it('sin cambios no deja guardar', () => {
    montar(['a@b.pe']);
    expect(screen.getByRole('button', { name: 'Guardar correos' })).toBeDisabled();
  });

  it('no tiene violaciones de axe', async () => {
    const { container } = montar(['a@b.pe']);
    expect(
      await axe(container, { rules: { 'color-contrast': { enabled: false } } }),
    ).toHaveNoViolations();
  });
});
