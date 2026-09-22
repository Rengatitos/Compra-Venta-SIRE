import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { listarComprobantesExternos, POR_PAGINA_EXTERNOS } from '@/api/comprobantesExternos';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button, ButtonLink } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { SelectField } from '@/components/ui/Field';
import { Pagination } from '@/components/ui/Pagination';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import {
  formatearFecha,
  formatearFechaHora,
  formatearMoneda,
  formatearPeriodo,
} from '@/lib/format';
import { ApiError } from '@/lib/http';
import type { ComprobanteExternoResponse } from '@/types/api';
import { LIBROS } from '@/types/domain';
import type { Libro } from '@/types/domain';

import { DialogComprobanteExterno } from './DialogComprobanteExterno';
import estilos from './ExternosPage.module.css';
import { identificador, presentarFuente } from './fuenteExterna';

const ETIQUETA_LIBRO: Record<Libro, string> = {
  compras: 'Compras',
  ventas: 'Ventas',
};

export function ExternosPage() {
  useDocumentTitle('Comprobantes externos');

  const ruc = useRuc();
  const [libro, setLibro] = useState<Libro>('ventas');
  const [periodo, setPeriodo] = useState('');
  const [pagina, setPagina] = useState(1);
  const [abierto, setAbierto] = useState<ComprobanteExternoResponse | null>(null);

  const consulta = useQuery({
    queryKey: ['comprobantes-externos', ruc, libro, periodo, pagina],
    queryFn: () => listarComprobantesExternos(ruc, { libro, periodo, pagina }),
  });

  function cambiarLibro(nuevo: Libro) {
    setLibro(nuevo);
    setPeriodo('');
    setPagina(1);
  }

  const filas = consulta.data?.items ?? [];
  const periodos = consulta.data?.periodos ?? [];

  const columnas: readonly Columna<ComprobanteExternoResponse>[] = [
    {
      clave: 'comprobante',
      cabecera: 'Comprobante',
      cabeceraDeFila: true,
      monoespaciada: true,
      render: (fila) => (
        <button type="button" className={estilos.enlace} onClick={() => setAbierto(fila)}>
          {identificador(fila)}
        </button>
      ),
    },
    {
      clave: 'fuente',
      cabecera: 'Fuente',
      render: (fila) => {
        const fuente = presentarFuente(fila.fuente);
        return <Badge tono={fuente.tono}>{fuente.texto}</Badge>;
      },
    },
    {
      clave: 'fecha',
      cabecera: 'Fecha',
      render: (fila) => formatearFecha(fila.fecha_operacion),
    },
    {
      clave: 'contraparte',
      cabecera: libro === 'ventas' ? 'Cliente' : 'Proveedor',
      anchoMinimo: '14rem',
      render: (fila) => fila.contraparte.nombre || '—',
    },
    {
      clave: 'total',
      cabecera: 'Total',
      numerica: true,
      render: (fila) => formatearMoneda(Number(fila.total), fila.moneda),
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: () => (
        <Badge tono="exito" conPunto>
          Recibido
        </Badge>
      ),
    },
    {
      clave: 'enviado',
      cabecera: 'Enviado',
      render: (fila) => formatearFechaHora(fila.enviado_en ?? fila.creado_en),
    },
  ];

  return (
    <>
      <PageHeader
        titulo="Comprobantes externos"
        descripcion="Lo que registraron las personas desde Apaclla Bot enviando la foto de un Yape, Plin, boleta o factura. Están aparte de lo que sincroniza el SIRE."
        acciones={
          <div className={estilos.libros} role="group" aria-label="Libro">
            {LIBROS.map((opcion) => (
              <Button
                key={opcion}
                pequeno
                pastilla
                variante={opcion === libro ? 'primario' : 'fantasma'}
                aria-pressed={opcion === libro}
                onClick={() => cambiarLibro(opcion)}
              >
                {ETIQUETA_LIBRO[opcion]}
              </Button>
            ))}
          </div>
        }
      />

      <Panel
        titulo={`${ETIQUETA_LIBRO[libro]} recibidas del bot`}
        descripcion={
          consulta.data
            ? `${consulta.data.total} comprobante${consulta.data.total === 1 ? '' : 's'}`
            : undefined
        }
        acciones={
          periodos.length > 0 ? (
            <div className={estilos.selector}>
              <SelectField
                etiqueta="Periodo"
                value={periodo}
                onChange={(evento) => {
                  setPeriodo(evento.target.value);
                  setPagina(1);
                }}
                opciones={[
                  { valor: '', texto: 'Todos los periodos' },
                  ...periodos.map((valor) => ({ valor, texto: formatearPeriodo(valor) })),
                ]}
              />
            </div>
          ) : null
        }
      >
        {consulta.isPending ? (
          <Skeleton lineas={5} etiqueta="Cargando comprobantes externos" />
        ) : null}

        {consulta.isError ? (
          <ErrorState
            titulo="No se pudieron cargar los comprobantes externos"
            texto={consulta.error instanceof ApiError ? consulta.error.message : undefined}
            accion={
              <Button pequeno onClick={() => void consulta.refetch()}>
                Reintentar
              </Button>
            }
          />
        ) : null}

        {consulta.data ? (
          <>
            <DataTable
              leyenda={`Comprobantes externos de ${ETIQUETA_LIBRO[libro].toLowerCase()}`}
              leyendaOculta
              columnas={columnas}
              filas={filas}
              claveDeFila={(fila) => fila.id}
              vacio={
                <EmptyState
                  titulo={
                    periodo
                      ? `Sin ${ETIQUETA_LIBRO[libro].toLowerCase()} del bot en ${formatearPeriodo(periodo)}`
                      : `Aún no llegan ${ETIQUETA_LIBRO[libro].toLowerCase()} desde el bot`
                  }
                  texto="Genera un código en Ajustes, vincula Apaclla Bot con el RUC de esta empresa y manda la foto de un comprobante desde el chat."
                  accion={
                    <ButtonLink a="/ajustes" pequeno>
                      Ir a Ajustes
                    </ButtonLink>
                  }
                />
              }
            />
            {consulta.data.total > POR_PAGINA_EXTERNOS ? (
              <Pagination
                pagina={pagina}
                haySiguiente={pagina * POR_PAGINA_EXTERNOS < consulta.data.total}
                onCambiar={setPagina}
              />
            ) : null}
          </>
        ) : null}
      </Panel>

      <DialogComprobanteExterno
        ruc={ruc}
        comprobante={abierto}
        onCerrar={() => setAbierto(null)}
      />
    </>
  );
}
