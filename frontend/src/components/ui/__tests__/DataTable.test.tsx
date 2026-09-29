import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DataTable } from '@/components/ui/DataTable';

interface Fila {
  id: string;
  origen: string;
}

const COLUMNAS = [{ clave: 'id', cabecera: 'Id', render: (fila: Fila) => fila.id }] as const;

describe('DataTable', () => {
  it('claseDeFila resalta sólo las filas que lo piden', () => {
    render(
      <DataTable<Fila>
        leyenda="Comprobantes"
        columnas={COLUMNAS}
        filas={[
          { id: 'F001-1', origen: 'sire' },
          { id: 'YAPE-1', origen: 'externo' },
        ]}
        claveDeFila={(fila) => fila.id}
        claseDeFila={(fila) => (fila.origen === 'externo' ? 'resaltada' : undefined)}
      />,
    );

    expect(screen.getByText('YAPE-1').closest('tr')).toHaveClass('resaltada');
    expect(screen.getByText('F001-1').closest('tr')).not.toHaveClass('resaltada');
  });
});
