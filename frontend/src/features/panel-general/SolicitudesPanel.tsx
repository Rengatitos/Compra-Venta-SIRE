import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import {
  descargarZipSolicitud,
  listarSolicitudes,
  obtenerSolicitud,
  reintentarSolicitud,
} from '@/api/solicitudes';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { type Columna, DataTable } from '@/components/ui/DataTable';
import { Dialog } from '@/components/ui/Dialog';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { Panel } from '@/components/ui/Panel';
import { ProgressBar } from '@/components/ui/Progress';
import { useToast } from '@/hooks/useToast';
import { formatearFechaHora, formatearPeriodo } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ItemSolicitud, SolicitudResponse } from '@/types/api';
import { ESTADOS_SOLICITUD_TERMINALES } from '@/types/domain';

import estilos from './SolicitudesPanel.module.css';
import {
  ETIQUETA_PASO,
  presentarEnvio,
  presentarItem,
  presentarPaso,
  presentarSolicitud,
} from './solicitudes';

const INTERVALO_MS = 5000;

function viva(solicitud: SolicitudResponse): boolean {
  return !ESTADOS_SOLICITUD_TERMINALES.includes(solicitud.estado);
}

function reintentable(solicitud: SolicitudResponse): boolean {
  return solicitud.estado === 'completada_con_errores' || solicitud.estado === 'fallida';
}

function useAcciones() {
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const reintentar = useMutation({
    mutationFn: (id: string) => reintentarSolicitud(id),
    onSuccess: async () => {
      mostrar({ tono: 'exito', titulo: 'Lo que falló vuelve a la cola' });
      await cliente.invalidateQueries({ queryKey: ['solicitudes'] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo reintentar',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  async function descargar(id: string) {
    try {
      await descargarZipSolicitud(id);
    } catch (fallo) {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo descargar el ZIP',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    }
  }

  return { reintentar, descargar };
}

/**
 * Solicitudes de procesamiento masivo: estado general, avance por empresa y
 * periodo, ZIP y correos. Se refresca sola mientras alguna sigue viva.
 */
export function SolicitudesPanel() {
  const [abierta, setAbierta] = useState<string | null>(null);
  const { reintentar, descargar } = useAcciones();

  const solicitudes = useQuery({
    queryKey: ['solicitudes'],
    queryFn: listarSolicitudes,
    refetchInterval: (consulta) => (consulta.state.data?.some(viva) ? INTERVALO_MS : false),
  });

  const columnas: readonly Columna<SolicitudResponse>[] = [
    {
      clave: 'fecha',
      cabecera: 'Pedida',
      monoespaciada: true,
      cabeceraDeFila: true,
      render: (s) => formatearFechaHora(s.creado_en),
    },
    { clave: 'por', cabecera: 'Por', render: (s) => s.creado_por },
    {
      clave: 'alcance',
      cabecera: 'Empresas × periodos',
      numerica: true,
      render: (s) => s.progreso.total,
    },
    {
      clave: 'estado',
      cabecera: 'Estado',
      anchoMinimo: '12rem',
      render: (s) => {
        const estado = presentarSolicitud(s.estado);
        return (
          <>
            <Badge tono={estado.tono} conPunto>
              {estado.texto}
            </Badge>
            <br />
            <span className={layout.textoSecundario}>
              {s.progreso.actual} de {s.progreso.total} terminados
            </span>
          </>
        );
      },
    },
    {
      clave: 'acciones',
      cabecera: 'Acciones',
      render: (s) => (
        <div className={layout.fila}>
          <Button pequeno variante="fantasma" onClick={() => setAbierta(s.id)}>
            Ver detalle
          </Button>
          {s.zip ? (
            <Button pequeno variante="secundario" onClick={() => void descargar(s.id)}>
              Descargar ZIP
            </Button>
          ) : null}
          {reintentable(s) ? (
            <Button
              pequeno
              variante="secundario"
              cargando={reintentar.isPending && reintentar.variables === s.id}
              onClick={() => reintentar.mutate(s.id)}
            >
              Reintentar fallidos
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <Panel
      titulo="Solicitudes"
      descripcion="Cada solicitud recorre, por empresa y periodo: descarga SIRE, comprobantes y clasificación con IA. Luego se generan los archivos, el ZIP y el correo."
    >
      {solicitudes.isPending ? (
        <Skeleton lineas={3} etiqueta="Cargando las solicitudes" />
      ) : null}
      {solicitudes.isError ? (
        <ErrorState
          titulo="No se pudieron cargar las solicitudes"
          texto={
            solicitudes.error instanceof ApiError
              ? solicitudes.error.message
              : 'Error inesperado.'
          }
        />
      ) : null}
      {solicitudes.data ? (
        <DataTable
          leyenda="Solicitudes de procesamiento masivo"
          leyendaOculta
          columnas={columnas}
          filas={solicitudes.data}
          claveDeFila={(s) => s.id}
          vacio={
            <EmptyState
              titulo="Sin solicitudes"
              texto="Marca empresas en la tabla y pulsa «Procesar» para lanzar la primera."
            />
          }
        />
      ) : null}
      <DetalleSolicitud id={abierta} onCerrar={() => setAbierta(null)} />
    </Panel>
  );
}

interface PropsDetalle {
  id: string | null;
  onCerrar: () => void;
}

function DetalleSolicitud({ id, onCerrar }: PropsDetalle) {
  const { reintentar, descargar } = useAcciones();
  const detalle = useQuery({
    queryKey: ['solicitudes', id],
    queryFn: () => obtenerSolicitud(id ?? ''),
    enabled: id !== null,
    refetchInterval: (consulta) =>
      consulta.state.data && viva(consulta.state.data) ? INTERVALO_MS : false,
  });
  const datos = detalle.data;

  const columnas: readonly Columna<ItemSolicitud>[] = [
    {
      clave: 'empresa',
      cabecera: 'Empresa',
      cabeceraDeFila: true,
      anchoMinimo: '12rem',
      render: (i) => (
        <>
          <span>{i.nombre ?? i.ruc}</span>
          <br />
          <span className={layout.textoSecundario}>{i.ruc}</span>
        </>
      ),
    },
    { clave: 'periodo', cabecera: 'Periodo', render: (i) => formatearPeriodo(i.periodo) },
    {
      clave: 'estado',
      cabecera: 'Estado',
      render: (i) => {
        const estado = presentarItem(i.estado);
        return (
          <Badge tono={estado.tono} conPunto>
            {estado.texto}
          </Badge>
        );
      },
    },
    {
      clave: 'pasos',
      cabecera: 'Pasos',
      anchoMinimo: '26rem',
      render: (i) => (
        <ul className={estilos.pasos}>
          {i.pasos.map((paso) => {
            const estado = presentarPaso(paso);
            const nota = paso.error ?? paso.nota ?? paso.mensaje;
            return (
              <li key={paso.paso} className={estilos.paso}>
                <span className={estilos.nombrePaso}>{ETIQUETA_PASO[paso.paso]}</span>
                <Badge tono={estado.tono}>{estado.texto}</Badge>
                {nota ? <span className={layout.textoSecundario}>{nota}</span> : null}
              </li>
            );
          })}
        </ul>
      ),
    },
  ];

  return (
    <Dialog
      abierto={id !== null}
      titulo={datos ? `Solicitud del ${formatearFechaHora(datos.creado_en)}` : 'Solicitud'}
      onCerrar={onCerrar}
      ancho="amplio"
      acciones={
        <>
          {datos?.zip ? (
            <Button variante="secundario" onClick={() => void descargar(datos.id)}>
              Descargar ZIP
            </Button>
          ) : null}
          {datos && reintentable(datos) ? (
            <Button
              variante="primario"
              cargando={reintentar.isPending}
              onClick={() => reintentar.mutate(datos.id)}
            >
              Reintentar fallidos
            </Button>
          ) : null}
          <Button variante="fantasma" onClick={onCerrar}>
            Cerrar
          </Button>
        </>
      }
    >
      {detalle.isPending && id ? (
        <Skeleton lineas={4} etiqueta="Cargando la solicitud" />
      ) : null}
      {datos ? (
        <div className={layout.pila}>
          <ProgressBar
            etiqueta="Empresas y periodos terminados"
            actual={datos.progreso.actual}
            total={datos.progreso.total}
            porcentaje={
              datos.progreso.total ? (datos.progreso.actual / datos.progreso.total) * 100 : 0
            }
            mensaje={presentarSolicitud(datos.estado).texto}
          />
          {datos.error ? (
            <ErrorState titulo="La solicitud terminó con error" texto={datos.error} />
          ) : null}
          <DataTable
            leyenda="Avance por empresa y periodo"
            columnas={columnas}
            filas={datos.items}
            claveDeFila={(i) => `${i.ruc}-${i.periodo}`}
          />
          {datos.envios.length ? (
            <DataTable
              leyenda="Correos"
              columnas={[
                {
                  clave: 'correo',
                  cabecera: 'Correo',
                  cabeceraDeFila: true,
                  render: (e) => e.correo,
                },
                {
                  clave: 'empresas',
                  cabecera: 'Empresas',
                  render: (e) => e.empresas.map((x) => x.nombre ?? x.ruc).join(', '),
                },
                {
                  clave: 'estado',
                  cabecera: 'Estado',
                  render: (e) => {
                    const estado = presentarEnvio(e.estado);
                    return (
                      <>
                        <Badge tono={estado.tono}>{estado.texto}</Badge>
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
                {
                  clave: 'modo',
                  cabecera: 'Entrega',
                  render: (e) =>
                    e.modo === 'adjunto' ? 'ZIP adjunto' : e.modo === 'enlace' ? 'Enlace' : '—',
                },
              ]}
              filas={datos.envios}
              claveDeFila={(e) => e.correo}
            />
          ) : null}
        </div>
      ) : null}
    </Dialog>
  );
}
