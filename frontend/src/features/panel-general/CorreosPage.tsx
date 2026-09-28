import { useQuery } from '@tanstack/react-query';

import { obtenerYo } from '@/api/usuarios';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState, Skeleton } from '@/components/ui/Feedback';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import layout from '@/styles/layouts.module.css';

import { ConfiguracionCorreo } from './ConfiguracionCorreo';
import { EnviosCorreo } from './EnviosCorreo';

export function CorreosPage() {
  useDocumentTitle('Correos');
  // El rol se consulta aquí y no con `useEsAdmin`, que responde «no» mientras
  // carga: así un administrador no ve un instante el aviso de «solo admins».
  const yo = useQuery({ queryKey: ['yo'], queryFn: obtenerYo, staleTime: 60_000 });

  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Correos"
        descripcion="Servidor, remitente y plantilla del correo que se envía al terminar cada solicitud, y a quién se enviaron los resultados."
      />
      {yo.isPending ? <Skeleton lineas={3} etiqueta="Comprobando tu rol" /> : null}
      {yo.data?.rol === 'admin' ? <ConfiguracionCorreo /> : null}
      {yo.data && yo.data.rol !== 'admin' ? (
        <EmptyState
          titulo="La configuración del correo es solo para administradores"
          texto="Pide a un administrador que configure el servidor SMTP y la plantilla."
        />
      ) : null}
      <EnviosCorreo />
    </div>
  );
}
