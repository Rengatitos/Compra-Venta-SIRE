import { useQuery } from '@tanstack/react-query';

import { listarEnvios } from '@/api/solicitudes';
import { Badge } from '@/components/ui/Badge';
import { type Columna, DataTable } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { Panel } from '@/components/ui/Panel';
import { formatearFechaHora, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { EnvioListado } from '@/types/api';

import { presentarEnvio } from './solicitudes';

/**
 * Registro de los correos con resultados: a quién se escribió, de qué
 * empresas y periodos, cuándo y cómo acabó el envío.
 */
export function EnviosCorreo() {
  const envios = useQuery({ queryKey: ['solicitudes', 'envios'], queryFn: listarEnvios });

  const columnas: readonly Columna<EnvioListado>[] = [
    { clave: 'correo', cabecera: 'Correo', cabeceraDeFila: true, render: (e) => e.correo },
    {
      clave: 'empresas',
      cabecera: 'Empresas asociadas',
      anchoMinimo: '14rem',
      render: (e) => e.empresas.map((x) => x.nombre ?? x.ruc).join(', '),
    },
    {
      clave: 'periodos',
      cabecera: 'Periodos procesados',
      anchoMinimo: '12rem',
      render: (e) => e.periodos.map(formatearPeriodo).join(', '),
    },
    {
      clave: 'fecha',
      cabecera: 'Fecha del proceso',
      monoespaciada: true,
      render: (e) => formatearFechaHora(e.enviado_en ?? e.solicitud_creada_en),
    },
    {
      clave: 'estado',
      cabecera: 'Estado del envío',
      anchoMinimo: '12rem',
      render: (e) => {
        const estado = presentarEnvio(e.estado);
        return (
          <>
            <Badge tono={estado.tono} conPunto>
              {estado.texto}
            </Badge>
            {e.error ? (
              <>
                <br />
                <span className={layout.textoSecundario}>{e.error}</span>
              </>
            ) : null}
          </>
        );
      },
    },
  ];

  return (
    <Panel
      titulo="Envíos de correo"
      descripcion="Correos con los resultados de las solicitudes. Los correos de cada empresa se configuran en sus Ajustes."
    >
      {envios.isPending ? <Skeleton lineas={3} etiqueta="Cargando los envíos" /> : null}
      {envios.isError ? (
        <ErrorState
          titulo="No se pudieron cargar los envíos"
          texto={envios.error instanceof ApiError ? envios.error.message : 'Error inesperado.'}
        />
      ) : null}
      {envios.data ? (
        <DataTable
          leyenda="Envíos de correo"
          leyendaOculta
          columnas={columnas}
          filas={envios.data}
          claveDeFila={(e) => `${e.solicitud_id}-${e.correo}`}
          vacio={
            <EmptyState
              titulo="Sin envíos todavía"
              texto="Al terminar una solicitud, aquí queda a quién se le enviaron los resultados."
            />
          }
        />
      ) : null}
    </Panel>
  );
}
