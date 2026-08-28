import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Link, useParams } from 'react-router';

import {
  actualizarDescripcion,
  exportarComprobante,
  obtenerComprobante,
} from '@/api/comprobantes';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { DataTable } from '@/components/ui/DataTable';
import type { Columna } from '@/components/ui/DataTable';
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback';
import { TextField } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { useRuc } from '@/features/auth/useAuth';
import { NoEncontradaPage } from '@/features/shared/NoEncontradaPage';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { useToast } from '@/hooks/useToast';
import { formatearFecha, formatearMoneda } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { AnalisisIA, LineaDetalle } from '@/types/api';
import type { FormatoExport } from '@/types/domain';
import { esPeriodoValido } from '@/types/domain';

import { presentarEstadoComprobante, presentarResultadoIA } from './estadoComprobante';

function Dato({ termino, children }: { termino: string; children: ReactNode }) {
  return (
    <div>
      <dt className={layout.termino}>{termino}</dt>
      <dd className={layout.descripcion}>{children}</dd>
    </div>
  );
}

/** `cantidad` e `importe` llegan como `Any` desde el backend: puede ser cualquier cosa. */
function textoCrudo(valor: unknown): string {
  if (valor === null || valor === undefined || valor === '') return '—';
  if (typeof valor === 'number' || typeof valor === 'boolean') return String(valor);
  if (typeof valor === 'string') return valor;
  return JSON.stringify(valor);
}

function FichaAnalisis({ analisis }: { analisis: AnalisisIA }) {
  const resultado = presentarResultadoIA(analisis.resultado);

  return (
    <dl className={layout.definiciones}>
      <Dato termino="Resultado">
        {resultado ? <Badge tono={resultado.tono}>{resultado.texto}</Badge> : '—'}
      </Dato>
      <Dato termino="Cuenta contable">{analisis.cuenta_contable ?? '—'}</Dato>
      <Dato termino="Centro de costos">{analisis.centro_costos ?? '—'}</Dato>
      <Dato termino="Condición IGV">{analisis.condicion_igv ?? '—'}</Dato>
      <Dato termino="Confianza">{analisis.confianza ?? '—'}</Dato>
      <Dato termino="Documentos de respaldo">
        {analisis.documentos === null ? '—' : analisis.documentos ? 'Sí' : 'No'}
      </Dato>
      <Dato termino="Observaciones">{analisis.observaciones ?? '—'}</Dato>
    </dl>
  );
}

export function ComprobanteDetallePage() {
  const { periodo = '', serieNumero = '' } = useParams();
  const ruc = useRuc();
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [descripcion, setDescripcion] = useState('');
  const [exportando, setExportando] = useState<FormatoExport | null>(null);

  useDocumentTitle(`Comprobante ${serieNumero}`);

  const valido = esPeriodoValido(periodo) && serieNumero !== '';

  const comprobante = useQuery({
    queryKey: ['comprobante', ruc, periodo, serieNumero],
    queryFn: () => obtenerComprobante(ruc, periodo, serieNumero),
    enabled: valido,
  });

  // El campo editable arranca con lo que la IA haya escrito.
  useEffect(() => {
    if (comprobante.data) {
      setDescripcion(comprobante.data.analisis?.descripcion ?? '');
    }
  }, [comprobante.data]);

  const guardar = useMutation({
    mutationFn: (texto: string) => actualizarDescripcion(ruc, periodo, serieNumero, texto),
    onSuccess: async (respuesta) => {
      mostrar({ tono: 'exito', titulo: respuesta.mensaje });
      await cliente.invalidateQueries({
        queryKey: ['comprobante', ruc, periodo, serieNumero],
      });
      await cliente.invalidateQueries({ queryKey: ['comprobantes', ruc, periodo] });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo guardar la descripción',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    },
  });

  if (!valido) return <NoEncontradaPage />;

  async function exportar(formato: FormatoExport) {
    setExportando(formato);
    try {
      await exportarComprobante(ruc, periodo, serieNumero, formato);
    } catch (fallo) {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo exportar el comprobante',
        detalle: fallo instanceof ApiError ? fallo.message : 'Error inesperado.',
      });
    } finally {
      setExportando(null);
    }
  }

  function alGuardar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    guardar.mutate(descripcion.trim());
  }

  const datos = comprobante.data;
  const estado = datos ? presentarEstadoComprobante(datos.estado_procesamiento) : null;

  const columnasDetalle: readonly Columna<LineaDetalle>[] = [
    {
      clave: 'producto',
      cabecera: 'Producto',
      cabeceraDeFila: true,
      render: (linea) => linea.producto ?? '—',
    },
    {
      clave: 'categoria_contable',
      cabecera: 'Categoría',
      render: (linea) => linea.categoria_contable ?? '—',
    },
    {
      clave: 'cantidad',
      cabecera: 'Cantidad',
      numerica: true,
      render: (linea) => textoCrudo(linea.cantidad),
    },
    {
      clave: 'importe',
      cabecera: 'Importe',
      numerica: true,
      render: (linea) => textoCrudo(linea.importe),
    },
    { clave: 'razon', cabecera: 'Razón', render: (linea) => linea.razon ?? '—' },
  ];

  return (
    <>
      <PageHeader
        titulo={serieNumero}
        descripcion={datos ? `${datos.tipo_cp_descripcion} · ${datos.razon_social || 's/n'}` : undefined}
        acciones={
          <>
            <Button
              onClick={() => void exportar('pdf')}
              cargando={exportando === 'pdf'}
              disabled={exportando !== null || !datos}
            >
              Exportar PDF
            </Button>
            <Button
              onClick={() => void exportar('excel')}
              cargando={exportando === 'excel'}
              disabled={exportando !== null || !datos}
            >
              Exportar Excel
            </Button>
          </>
        }
      />

      <div className={layout.pilaAmplia}>
        {comprobante.isPending ? (
          <Panel titulo="Cargando comprobante">
            <Skeleton lineas={5} etiqueta="Cargando comprobante" />
          </Panel>
        ) : null}

        {comprobante.isError ? (
          <ErrorState
            titulo={
              comprobante.error instanceof ApiError && comprobante.error.esNoEncontrado
                ? 'Comprobante no encontrado'
                : 'No se pudo cargar el comprobante'
            }
            texto={
              comprobante.error instanceof ApiError
                ? comprobante.error.message
                : 'Error inesperado.'
            }
            accion={
              <Link to={`/periodos/${encodeURIComponent(periodo)}`}>
                Volver al listado del periodo
              </Link>
            }
          />
        ) : null}

        {datos ? (
          <>
            <Panel
              titulo="Datos del comprobante"
              acciones={
                estado ? (
                  <Badge tono={estado.tono} conPunto>
                    {estado.texto}
                  </Badge>
                ) : null
              }
            >
              <dl className={layout.definiciones}>
                <Dato termino="Tipo">
                  {datos.tipo_cp} · {datos.tipo_cp_descripcion}
                </Dato>
                <Dato termino="Serie y número">{datos.serie_numero}</Dato>
                <Dato termino="Contraparte">{datos.razon_social || '—'}</Dato>
                <Dato termino="Documento">
                  {datos.documento_contraparte || '—'}
                  {datos.tipo_doc_identidad ? ` (tipo ${datos.tipo_doc_identidad})` : ''}
                </Dato>
                <Dato termino="Emisión">{formatearFecha(datos.fecha_emision)}</Dato>
                <Dato termino="Vencimiento">{formatearFecha(datos.fecha_vencimiento)}</Dato>
                <Dato termino="Libro">{datos.libro}</Dato>
                <Dato termino="Origen">{datos.origen}</Dato>
              </dl>
            </Panel>

            <Panel titulo="Importes">
              <dl className={layout.definiciones}>
                <Dato termino="Base imponible">
                  {formatearMoneda(datos.base_imponible, datos.moneda)}
                </Dato>
                <Dato termino="IGV">{formatearMoneda(datos.igv, datos.moneda)}</Dato>
                <Dato termino="Exonerado">
                  {formatearMoneda(datos.exonerado, datos.moneda)}
                </Dato>
                <Dato termino="Inafecto">{formatearMoneda(datos.inafecto, datos.moneda)}</Dato>
                <Dato termino="Otros tributos">
                  {formatearMoneda(datos.otros_tributos, datos.moneda)}
                </Dato>
                <Dato termino="Total">{formatearMoneda(datos.total, datos.moneda)}</Dato>
              </dl>
            </Panel>

            <Panel
              titulo="Clasificación de la IA"
              descripcion="Estos campos los genera el análisis con Gemini. El único editable es la descripción."
            >
              {datos.analisis ? (
                <FichaAnalisis analisis={datos.analisis} />
              ) : (
                <EmptyState
                  titulo="Este comprobante aún no se ha analizado"
                  texto="Lanza el análisis con IA para el periodo y vuelve a esta ficha."
                  accion={
                    <Link to={`/periodos/${encodeURIComponent(periodo)}/analisis`}>
                      Ir al análisis con IA
                    </Link>
                  }
                />
              )}
            </Panel>

            <Panel
              titulo="Descripción"
              descripcion="Se guarda dentro del análisis sin sobrescribir el resto de los campos generados por la IA."
            >
              <form className={layout.pila} onSubmit={alGuardar}>
                <TextField
                  etiqueta="Descripción del comprobante"
                  name="descripcion"
                  value={descripcion}
                  onChange={(evento) => setDescripcion(evento.target.value)}
                  maxLength={500}
                  ayuda="Texto libre para el equipo contable."
                />
                <div className={layout.filaFin}>
                  <Button type="submit" variante="primario" cargando={guardar.isPending}>
                    Guardar descripción
                  </Button>
                </div>
              </form>
            </Panel>

            {datos.analisis && datos.analisis.detalle.length > 0 ? (
              <Panel titulo="Líneas clasificadas">
                <DataTable
                  leyenda={`Líneas clasificadas por la IA para ${serieNumero}`}
                  leyendaOculta
                  columnas={columnasDetalle}
                  filas={datos.analisis.detalle}
                  claveDeFila={(linea) => `${linea.producto ?? ''}-${textoCrudo(linea.importe)}`}
                />
              </Panel>
            ) : null}

            <Panel
              titulo="Detalle extraído de SUNAT"
              descripcion="Ítems obtenidos del portal SOL. La API SIRE no expone este detalle línea por línea."
            >
              {datos.detalle_sunat.length > 0 ? (
                <pre className={layout.preformateado}>
                  {JSON.stringify(datos.detalle_sunat, null, 2)}
                </pre>
              ) : (
                <EmptyState
                  titulo="Sin detalle extraído"
                  texto="Lanza la extracción de detalle del periodo para traer los ítems de este comprobante."
                  accion={
                    <Link to={`/periodos/${encodeURIComponent(periodo)}/detalle`}>
                      Ir a la extracción de detalle
                    </Link>
                  }
                />
              )}
            </Panel>
          </>
        ) : null}
      </div>
    </>
  );
}
