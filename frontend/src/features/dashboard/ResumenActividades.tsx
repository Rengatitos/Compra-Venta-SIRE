import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';

import { obtenerEmpresa } from '@/api/empresas';
import { ANCLA_ACTIVIDADES, principalEfectiva } from '@/features/empresa/actividades';

import estilos from './ResumenActividades.module.css';

/**
 * Con qué actividades clasifica la IA esta empresa, a la vista en el inicio.
 * La ficha de SUNAT no siempre describe el negocio real, y es lo primero que
 * conviene revisar cuando una clasificación sale rara: por eso el «editar»
 * lleva directo al panel de Ajustes.
 */
export function ResumenActividades({ ruc }: { ruc: string }) {
  const empresa = useQuery({ queryKey: ['empresa', ruc], queryFn: () => obtenerEmpresa(ruc) });
  if (!empresa.data) return null;

  const actividades = empresa.data.actividades_economicas ?? [];
  const principal = principalEfectiva(empresa.data);
  const otras = actividades.filter((a) => a.ciiu !== principal);
  const deLaPrincipal = actividades.find((a) => a.ciiu === principal);

  return (
    <p className={estilos.resumen}>
      <span className={estilos.etiqueta}>Actividad para clasificar:</span>{' '}
      {deLaPrincipal ? (
        <strong>
          {deLaPrincipal.ciiu} · {deLaPrincipal.descripcion || 'Sin descripción'}
        </strong>
      ) : (
        <span>sin actividades registradas</span>
      )}
      {otras.length > 0 ? (
        <span className={estilos.otras}> · También: {otras.map((a) => a.ciiu).join(', ')}</span>
      ) : null}{' '}
      <Link to={`/ajustes#${ANCLA_ACTIVIDADES}`} className={estilos.editar}>
        editar
      </Link>
    </p>
  );
}
