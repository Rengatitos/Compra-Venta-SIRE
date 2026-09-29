import { useQuery } from '@tanstack/react-query';

import { obtenerYo } from '@/api/usuarios';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState, Skeleton } from '@/components/ui/Feedback';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import layout from '@/styles/layouts.module.css';

import { ConfiguracionCorreo } from './ConfiguracionCorreo';
import { EnviosCorreo } from './EnviosCorreo';
import { EnvioResultados } from './EnvioResultados';
import estilos from './EnvioResultados.module.css';

export function CorreosPage() {
  useDocumentTitle('Correos');
  // El rol se consulta aquí y no con `useEsAdmin`, que responde «no» mientras
  // carga: así un administrador no ve un instante el aviso de «solo admins».
  const yo = useQuery({ queryKey: ['yo'], queryFn: obtenerYo, staleTime: 60_000 });

  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Correos"
        descripcion="A dónde llegan los resultados de cada procesamiento masivo y qué se envió."
      />
      {yo.isPending ? <Skeleton lineas={3} etiqueta="Comprobando tu rol" /> : null}
      {yo.data?.rol === 'admin' ? (
        <>
          <EnvioResultados />
          {/* Cerrado por defecto: con la cuenta del sistema no hace falta
              tocar el servidor ni la plantilla. */}
          <details className={estilos.avanzadas}>
            <summary>
              Opciones avanzadas
              <span>Servidor SMTP, plantilla del mensaje y límites</span>
            </summary>
            <div className={estilos.contenidoAvanzado}>
              <ConfiguracionCorreo />
            </div>
          </details>
        </>
      ) : null}
      {yo.data && yo.data.rol !== 'admin' ? (
        <EmptyState
          titulo="La configuración del correo es solo para administradores"
          texto="Pide a un administrador que la revise."
        />
      ) : null}
      <EnviosCorreo />
    </div>
  );
}
