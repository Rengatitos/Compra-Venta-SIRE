import { PageHeader } from '@/components/layout/PageHeader';
import { ButtonLink } from '@/components/ui/Button';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import layout from '@/styles/layouts.module.css';

import { ProcesamientoMasivo } from './ProcesamientoMasivo';
import { useSeleccion } from './seleccionContext';
import { useResumenEmpresas } from './useResumenEmpresas';

/**
 * Lanza el procesamiento de las empresas marcadas en «Empresas». La selección
 * vive en el armazón del panel general, así que llega intacta hasta aquí.
 */
export function ProcesamientoMasivoPage() {
  useDocumentTitle('Procesamiento masivo');
  const { seleccion, setSeleccion } = useSeleccion();
  const { empresas } = useResumenEmpresas();

  // Solo cuentan las que siguen existiendo.
  const marcadas = empresas.filter((e) => seleccion.has(e.ruc));
  const todas = empresas.length > 0 && marcadas.length === empresas.length;

  return (
    <div className={layout.pilaAmplia}>
      <PageHeader
        titulo="Procesamiento masivo"
        descripcion={
          marcadas.length
            ? marcadas.map((e) => e.nombre ?? e.ruc).join(', ')
            : 'Todavía no hay empresas marcadas.'
        }
        acciones={
          <ButtonLink a="/" variante="fantasma" pequeno>
            {marcadas.length ? 'Cambiar selección' : 'Elegir empresas'}
          </ButtonLink>
        }
      />
      <ProcesamientoMasivo
        seleccionados={marcadas.map((e) => e.ruc)}
        todas={todas}
        onEnviada={() => setSeleccion(new Set())}
      />
    </div>
  );
}
