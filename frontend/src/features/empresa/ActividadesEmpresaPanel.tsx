import { useMutation, useQueryClient } from '@tanstack/react-query';

import { obtenerCiiuEmpresa } from '@/api/empresas';
import { Button } from '@/components/ui/Button';
import { Panel } from '@/components/ui/Panel';
import { useToast } from '@/hooks/useToast';
import { formatearFechaHora } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { EmpresaResponse } from '@/types/api';

/**
 * Actividades económicas (CIIU) de la ficha RUC de la empresa. Son el contexto
 * con el que el clasificador contable interpreta cada comprobante; el botón
 * vuelve a leerlas de la Consulta RUC de SUNAT y reemplaza las guardadas.
 */
export function ActividadesEmpresaPanel({
  ruc,
  empresa,
}: {
  ruc: string;
  empresa: EmpresaResponse | undefined;
}) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const obtener = useMutation({
    mutationFn: () => obtenerCiiuEmpresa(ruc),
    onSuccess: async (actualizada) => {
      const total = actualizada.actividades_economicas?.length ?? 0;
      mostrar({
        tono: 'exito',
        titulo: `${total} ${total === 1 ? 'actividad económica' : 'actividades económicas'} obtenidas de SUNAT`,
      });
      await cliente.invalidateQueries({ queryKey: ['empresa', ruc] });
    },
    onError: (fallo) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudo consultar la ficha RUC',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      }),
  });

  const actividades = empresa?.actividades_economicas ?? [];
  const ficha = empresa?.ficha_ruc;

  return (
    <Panel
      titulo="Actividades económicas (CIIU)"
      descripcion="Salen de la Consulta RUC de SUNAT. El clasificador contable las usa para interpretar cada comprobante y proponer su cuenta."
      acciones={
        <Button onClick={() => obtener.mutate()} cargando={obtener.isPending}>
          Obtener CIIU desde SUNAT
        </Button>
      }
    >
      {actividades.length > 0 ? (
        <ul className={layout.pila}>
          {actividades.map((actividad) => (
            <li key={`${actividad.tipo}-${actividad.ciiu}`}>
              <strong>
                {actividad.tipo === 'PRINCIPAL' ? 'Principal' : 'Secundaria'} · {actividad.ciiu}
              </strong>{' '}
              — {actividad.descripcion || 'Sin descripción'}
            </li>
          ))}
        </ul>
      ) : (
        <p className={layout.textoSecundario}>
          Aún no hay actividades guardadas. Mientras tanto se usa el CIIU principal del token de
          SUNAT, si lo hay; la primera clasificación también las consulta sola.
        </p>
      )}
      {ficha ? (
        <p className={layout.textoSecundario}>
          {[ficha.razon_social, ficha.estado, ficha.condicion].filter(Boolean).join(' · ')} ·
          consultado {formatearFechaHora(ficha.consultado_en)}
        </p>
      ) : null}
    </Panel>
  );
}
