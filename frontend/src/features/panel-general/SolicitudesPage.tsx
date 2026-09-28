import { PageHeader } from '@/components/layout/PageHeader';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import layout from '@/styles/layouts.module.css';

import { SolicitudesPanel } from './SolicitudesPanel';

export function SolicitudesPage() {
  useDocumentTitle('Solicitudes');

  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Solicitudes"
        descripcion="Cada procesamiento masivo lanzado, con su avance por empresa y periodo."
      />
      <SolicitudesPanel />
    </div>
  );
}
