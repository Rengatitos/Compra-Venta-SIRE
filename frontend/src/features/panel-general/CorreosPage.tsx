import { PageHeader } from '@/components/layout/PageHeader';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import layout from '@/styles/layouts.module.css';

import { EnviosCorreo } from './EnviosCorreo';

export function CorreosPage() {
  useDocumentTitle('Correos');

  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Correos"
        descripcion="A quién se enviaron los resultados de cada solicitud."
      />
      <EnviosCorreo />
    </div>
  );
}
