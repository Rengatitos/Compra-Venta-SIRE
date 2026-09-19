import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { ContextoEmpresasReact } from '@/features/empresas/empresasContext';
import { SelectorEmpresa } from '@/features/empresas/SelectorEmpresa';
import type { EmpresaResponse } from '@/types/api';

// `jsdom` no tiene canvas, así que el contraste se verifica en el navegador.
const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

/** `jsdom` no implementa `showModal`/`close`, que es lo único que `Dialog` delega. */
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function abrir(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function cerrar(this: HTMLDialogElement) {
    this.open = false;
  };
});

function empresa(ruc: string, nombre: string | null): EmpresaResponse {
  return {
    id: ruc,
    ruc,
    nombre,
    usuario: 'USUARIO',
    fecha_creacion: null,
    rubro: 'Comercio',
  };
}

const ALFA = empresa('20603391692', 'Alfa');
const BETA = empresa('20610202251', 'Beta');

function montar(empresas: EmpresaResponse[], cambiarEmpresa = vi.fn()) {
  const utilidades = render(
    <MemoryRouter>
      <ContextoEmpresasReact.Provider
        value={{
          empresas,
          ruc: empresas[0]?.ruc ?? null,
          empresaActiva: empresas[0] ?? null,
          cambiarEmpresa,
          recargar: () => undefined,
        }}
      >
        <SelectorEmpresa />
      </ContextoEmpresasReact.Provider>
    </MemoryRouter>,
  );
  return { ...utilidades, cambiarEmpresa };
}

describe('selector de empresa', () => {
  it('el RUC no basta: dice con palabras cuál es la empresa activa', () => {
    montar([ALFA, BETA]);

    expect(screen.getByRole('button', { name: /Empresa activa: 20603391692/ })).toBeInTheDocument();
  });

  it('con una sola empresa no pinta un botón que no lleva a ningún sitio', () => {
    montar([ALFA]);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('20603391692')).toBeInTheDocument();
  });

  it('abre el diálogo y lista las cuentas', async () => {
    montar([ALFA, BETA]);

    await userEvent.click(screen.getByRole('button', { name: /Empresa activa/ }));

    const dialogo = screen.getByRole('dialog', { name: 'Cambiar de empresa' });
    expect(dialogo).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Beta/ })).toBeInTheDocument();
  });

  it('marca la activa con palabras, no solo con color', async () => {
    montar([ALFA, BETA]);

    await userEvent.click(screen.getByRole('button', { name: /Empresa activa/ }));

    const opcion = screen.getByRole('button', { name: /Alfa/ });
    expect(opcion).toHaveAttribute('aria-current', 'true');
    expect(opcion).toHaveTextContent('Activa');
  });

  it('filtra la lista y anuncia cuántas coinciden', async () => {
    montar([ALFA, BETA]);
    await userEvent.click(screen.getByRole('button', { name: /Empresa activa/ }));

    await userEvent.type(screen.getByLabelText(/Filtrar/), 'Beta');

    expect(screen.queryByRole('button', { name: /Alfa/ })).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('1 empresa coincide');
  });

  it('elegir otra cuenta la comunica y cierra el diálogo', async () => {
    const { cambiarEmpresa } = montar([ALFA, BETA]);
    await userEvent.click(screen.getByRole('button', { name: /Empresa activa/ }));

    await userEvent.click(screen.getByRole('button', { name: /Beta/ }));

    expect(cambiarEmpresa).toHaveBeenCalledWith(BETA.ruc);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('el diálogo abierto no tiene violaciones de axe', async () => {
    const { container } = montar([ALFA, BETA]);
    await userEvent.click(screen.getByRole('button', { name: /Empresa activa/ }));

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });
});
