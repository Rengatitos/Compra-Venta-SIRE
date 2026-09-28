import { PageHeader } from '@/components/layout/PageHeader';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import layout from '@/styles/layouts.module.css';

import { HistorialDescargas } from './HistorialDescargas';
import { useResumenEmpresas } from './useResumenEmpresas';

export function HistorialPage() {
  useDocumentTitle('Historial');
  const { nombres } = useResumenEmpresas();

  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Historial"
        descripcion="Los procesos en segundo plano de todas las empresas."
      />
      <HistorialDescargas nombres={nombres} />
    </div>
  );
}
