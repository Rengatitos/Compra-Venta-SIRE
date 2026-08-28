import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { axe } from 'vitest-axe';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, MetricTile } from '@/components/ui/Feedback';
import { SelectField, TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/Progress';
import { ThemeToggle } from '@/components/ui/ThemeToggle';

/**
 * jsdom no implementa canvas, así que axe no puede calcular contraste aquí: esa
 * comprobación se hace en el navegador (ver la sección de verificación del
 * README). El resto de las reglas sí son fiables en este entorno.
 */
const OPCIONES = { rules: { 'color-contrast': { enabled: false } } } as const;

interface Fila {
  serie: string;
  total: number;
}

const COLUMNAS: readonly Columna<Fila>[] = [
  { clave: 'serie', cabecera: 'Comprobante', cabeceraDeFila: true, render: (f) => f.serie },
  { clave: 'total', cabecera: 'Total', numerica: true, render: (f) => String(f.total) },
];

const FILAS: Fila[] = [
  { serie: 'F001-1', total: 118 },
  { serie: 'F001-2', total: 236 },
];

describe('accesibilidad de los primitivos de interfaz', () => {
  it('un panel con tabla no tiene violaciones de axe', async () => {
    const { container } = render(
      <Panel titulo="Comprobantes" descripcion="Listado del periodo">
        <DataTable
          leyenda="Comprobantes del periodo 202606"
          columnas={COLUMNAS}
          filas={FILAS}
          claveDeFila={(fila) => fila.serie}
        />
      </Panel>,
    );

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });

  it('un formulario con etiquetas, ayuda y error no tiene violaciones', async () => {
    const { container } = render(
      <form>
        <TextField
          etiqueta="RUC"
          value="2060899"
          onChange={() => undefined}
          ayuda="11 dígitos."
          error="El RUC debe tener 11 dígitos."
          required
        />
        <SelectField
          etiqueta="Libro"
          value="compras"
          onChange={() => undefined}
          opciones={[
            { valor: 'compras', texto: 'Compras (RCE)' },
            { valor: 'ventas', texto: 'Ventas (RVIE) — no disponible', deshabilitada: true },
          ]}
        />
        <Button type="submit" variante="primario">
          Enviar
        </Button>
      </form>,
    );

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });

  it('los estados de feedback y el progreso no tienen violaciones', async () => {
    const { container } = render(
      <div>
        <MetricTile etiqueta="Comprobantes" valor="128" nota="Periodo 202606" />
        <Badge tono="exito" conPunto>
          Analizado
        </Badge>
        <ProgressBar
          etiqueta="Avance de la extracción"
          actual={4}
          total={10}
          porcentaje={40}
          mensaje="Extrayendo detalle de 10 comprobantes"
        />
        <EmptyState titulo="Sin datos" texto="Sincroniza la propuesta." />
        <ErrorState titulo="Error" texto="No se pudo cargar." />
        <ThemeToggle />
      </div>,
    );

    expect(await axe(container, OPCIONES)).toHaveNoViolations();
  });
});

describe('conmutador de tema', () => {
  it('el icono no basta: el botón nombra la acción con palabras', () => {
    render(<ThemeToggle />);
    // Arranca en claro, así que la acción disponible es pasar a oscuro.
    expect(screen.getByRole('button', { name: 'Activar el modo oscuro' })).toBeInTheDocument();
  });

  it('cambia de acción al pulsarlo', async () => {
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole('button', { name: 'Activar el modo oscuro' }));

    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(screen.getByRole('button', { name: 'Activar el modo claro' })).toBeInTheDocument();
  });
});
