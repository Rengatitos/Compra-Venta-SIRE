import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { axe } from 'vitest-axe';

import { Checkbox } from '@/components/ui/Checkbox';

describe('Checkbox', () => {
  it('se marca desde su etiqueta', async () => {
    const alCambiar = vi.fn();
    render(<Checkbox etiqueta="Clasificar con IA" onChange={alCambiar} />);

    await userEvent.click(screen.getByText('Clasificar con IA'));

    expect(alCambiar).toHaveBeenCalledOnce();
  });

  it('la etiqueta oculta se sigue leyendo', () => {
    render(<Checkbox etiqueta="Procesar Alfa" etiquetaOculta />);
    expect(screen.getByRole('checkbox', { name: 'Procesar Alfa' })).toBeInTheDocument();
  });

  it('refleja el estado indeterminado del «seleccionar todas»', () => {
    render(<Checkbox etiqueta="Todas" indeterminado readOnly />);
    expect(screen.getByRole<HTMLInputElement>('checkbox').indeterminate).toBe(true);
  });

  it('no tiene violaciones de axe', async () => {
    const { container } = render(<Checkbox etiqueta="Todas" ayuda="Incluye las filtradas" />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
