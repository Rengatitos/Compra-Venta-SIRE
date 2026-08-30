import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useContext, useEffect } from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { ToastProvider } from '../ToastProvider';
import { ContextoAvisosReact } from '@/hooks/toastContext';
import type { Aviso } from '@/hooks/toastContext';

/** Dispara un aviso al montar, que es como lo usan las páginas. */
function Disparador({ aviso }: { aviso: Omit<Aviso, 'id'> }) {
  const contexto = useContext(ContextoAvisosReact);
  useEffect(() => {
    contexto?.mostrar(aviso);
    // Sólo al montar: repetirlo apilaría avisos en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

function montar(aviso: Omit<Aviso, 'id'>) {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <Disparador aviso={aviso} />
      </ToastProvider>
    </MemoryRouter>,
  );
}

describe('avisos', () => {
  it('muestra el título y el detalle', () => {
    montar({ tono: 'exito', titulo: 'Extracción iniciada', detalle: 'El avance sale aquí.' });

    expect(screen.getByText('Extracción iniciada')).toBeInTheDocument();
    expect(screen.getByText('El avance sale aquí.')).toBeInTheDocument();
  });

  it('lleva a donde ocurre lo que anuncia', () => {
    // El aviso de extracción decía "consulta su avance en /api/v1/jobs/{job_id}":
    // una ruta de API, con el marcador sin sustituir, que además no llevaba a
    // ningún sitio. Ahora el aviso ofrece el enlace real.
    montar({
      tono: 'exito',
      titulo: 'Extracción iniciada',
      detalle: 'El avance aparece en esta misma página mientras corre.',
      accion: { texto: 'Ver en Procesos', a: '/procesos' },
    });

    const enlace = screen.getByRole('link', { name: 'Ver en Procesos' });
    expect(enlace).toHaveAttribute('href', '/procesos');
  });

  it('no pinta enlace cuando el aviso no trae acción', () => {
    montar({ tono: 'error', titulo: 'No se pudo iniciar' });

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('seguir el enlace cierra el aviso', async () => {
    // Dejarlo abierto encima de la página de destino tapa justo lo que el
    // usuario acaba de pedir ver.
    montar({
      tono: 'exito',
      titulo: 'Extracción iniciada',
      accion: { texto: 'Ver en Procesos', a: '/procesos' },
    });

    await userEvent.click(screen.getByRole('link', { name: 'Ver en Procesos' }));

    expect(screen.queryByText('Extracción iniciada')).not.toBeInTheDocument();
  });
});
