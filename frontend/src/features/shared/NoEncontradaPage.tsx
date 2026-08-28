import { Link } from 'react-router';

import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/ui/Feedback';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

export function NoEncontradaPage() {
  useDocumentTitle('Página no encontrada');

  return (
    <>
      <PageHeader titulo="Esta página no existe" />
      <EmptyState
        titulo="No encontramos lo que buscabas"
        texto="La dirección no corresponde a ninguna sección de la aplicación."
        accion={<Link to="/">Volver al dashboard</Link>}
      />
    </>
  );
}
