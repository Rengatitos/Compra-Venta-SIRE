import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Link } from 'react-router';

import { actualizarDescripcion } from '@/api/comprobantes';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/Feedback';
import { TextAreaField } from '@/components/ui/Field';
import { useToast } from '@/hooks/useToast';
import { formatearFecha, formatearMoneda } from '@/lib/format';
import { ApiError } from '@/lib/http';
import layout from '@/styles/layouts.module.css';
import type { ComprobanteResponse } from '@/types/api';

import { presentarEstadoComprobante } from './estadoComprobante';
import estilos from './FichaComprobante.module.css';
import { TablaDetalleSunat } from './TablaDetalleSunat';

function Dato({
  termino,
  children,
  className,
}: {
  termino: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className={layout.termino}>{termino}</dt>
      <dd className={layout.descripcion}>{children}</dd>
    </div>
  );
}

/**
 * Un comprobante tiene desglose que mostrar solo si alguna adquisición fue a
 * parar a operaciones no gravadas. Si todo es DG, el desglose es la base y no
 * aporta nada.
 */
function hayDesglose(datos: ComprobanteResponse): boolean {
  return (
    datos.base_imponible_dgng !== 0 ||
    datos.igv_dgng !== 0 ||
    datos.base_imponible_dng !== 0 ||
    datos.igv_dng !== 0
  );
}

function Seccion({
  titulo,
  acciones,
  children,
}: {
  titulo: string;
  acciones?: ReactNode;
  children: ReactNode;
}) {
  const idTitulo = useId();

  return (
    <section className={estilos.seccion} aria-labelledby={idTitulo}>
      <div className={estilos.cabecera}>
        <h3 className={estilos.titulo} id={idTitulo}>
          {titulo}
        </h3>
        {acciones}
      </div>
      {children}
    </section>
  );
}

interface Props {
  datos: ComprobanteResponse;
  ruc: string;
  periodo: string;
}

/** Cuerpo del modal de un comprobante. La carga y las acciones las lleva quien lo abre. */
export function FichaComprobante({ datos, ruc, periodo }: Props) {
  const cliente = useQueryClient();
  const { mostrar } = useToast();

  const [descripcion, setDescripcion] = useState('');

  const serieNumero = datos.serie_numero;
  const estado = presentarEstadoComprobante(datos.estado_procesamiento);

  // El campo editable arranca con la glosa extraída.
  useEffect(() => {
    setDescripcion(datos.glosa ?? '');
  }, [datos]);

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

  function alGuardar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    guardar.mutate(descripcion.trim());
  }

  return (
    <>
      <Seccion
        titulo="Datos del comprobante"
        acciones={
          <Badge tono={estado.tono} conPunto>
            {estado.texto}
          </Badge>
        }
      >
        <dl className={layout.definiciones}>
          <Dato termino="Tipo">
            {datos.tipo_cp} · {datos.tipo_cp_descripcion}
          </Dato>
          <Dato termino="Contraparte">{datos.razon_social || '—'}</Dato>
          <Dato termino="Documento">
            {datos.documento_contraparte || '—'}
            {datos.tipo_doc_identidad ? ` (tipo ${datos.tipo_doc_identidad})` : ''}
          </Dato>
          <Dato termino="Emisión">{formatearFecha(datos.fecha_emision)}</Dato>
          <Dato termino="Vencimiento">{formatearFecha(datos.fecha_vencimiento)}</Dato>
          <Dato termino="Libro">{datos.libro}</Dato>
          <Dato termino="Origen">{datos.origen}</Dato>
          <Dato termino="PDF de SUNAT">
            {datos.pdf_sunat?.ruta
              ? `Guardado · ${Math.max(1, Math.round(datos.pdf_sunat.bytes / 1024))} KB`
              : 'Sin descargar'}
          </Dato>
        </dl>
      </Seccion>

      <Seccion titulo="Importes">
        <dl className={layout.definiciones}>
          <Dato termino="Base imponible">
            {formatearMoneda(datos.base_imponible, datos.moneda)}
          </Dato>
          <Dato termino="IGV">{formatearMoneda(datos.igv, datos.moneda)}</Dato>
          {/*
            El desglose por destino solo aparece cuando hay algo que desglosar.
            En la inmensa mayoría de comprobantes todo va a «gravadas» y
            repetir la base imponible en tres filas idénticas sería ruido.
          */}
          {hayDesglose(datos) ? (
            <>
              <Dato termino="Gravadas (DG)">
                {formatearMoneda(datos.base_imponible_dg, datos.moneda)} ·{' '}
                {formatearMoneda(datos.igv_dg, datos.moneda)} de IGV
              </Dato>
              <Dato termino="Gravadas y no gravadas (DGNG)">
                {formatearMoneda(datos.base_imponible_dgng, datos.moneda)} ·{' '}
                {formatearMoneda(datos.igv_dgng, datos.moneda)} de IGV
              </Dato>
              <Dato termino="No gravadas (DNG)">
                {formatearMoneda(datos.base_imponible_dng, datos.moneda)} ·{' '}
                {formatearMoneda(datos.igv_dng, datos.moneda)} de IGV
              </Dato>
            </>
          ) : null}
          {datos.porcentaje_igv !== null ? (
            <Dato termino="Tasa IGV">{datos.porcentaje_igv} %</Dato>
          ) : null}
          <Dato termino="Exonerado">{formatearMoneda(datos.exonerado, datos.moneda)}</Dato>
          <Dato termino="Inafecto">{formatearMoneda(datos.inafecto, datos.moneda)}</Dato>
          <Dato termino="No gravado">{formatearMoneda(datos.no_gravado, datos.moneda)}</Dato>
          <Dato termino="ICBPER">{formatearMoneda(datos.icbper, datos.moneda)}</Dato>
          <Dato termino="Otros tributos">
            {formatearMoneda(datos.otros_tributos, datos.moneda)}
          </Dato>
          <Dato termino="Total">{formatearMoneda(datos.total, datos.moneda)}</Dato>
        </dl>
      </Seccion>

      <Seccion titulo="Descripción">
        <form className={layout.pila} onSubmit={alGuardar}>
          <TextAreaField
            etiqueta="Descripción del comprobante"
            name="descripcion"
            value={descripcion}
            onChange={(evento) => setDescripcion(evento.target.value)}
            maxLength={500}
            rows={4}
            ayuda="Texto libre para el equipo contable. Se guarda como glosa del comprobante."
          />
          <div className={layout.filaFin}>
            <Button type="submit" cargando={guardar.isPending}>
              Guardar descripción
            </Button>
          </div>
        </form>
      </Seccion>

      <Seccion titulo="Detalle extraído de SUNAT">
        <TablaDetalleSunat
          filas={datos.detalle_sunat}
          moneda={datos.moneda}
          serieNumero={serieNumero}
          periodo={periodo}
        />
      </Seccion>
    </>
  );
}

/** Enlace de respaldo por si alguien llega con un `serie_numero` que ya no existe. */
export function ComprobanteNoEncontrado({ periodo }: { periodo: string }) {
  return (
    <EmptyState
      titulo="Comprobante no encontrado"
      texto="Puede que se haya eliminado el periodo o que la serie ya no exista."
      accion={<Link to={`/periodos/${encodeURIComponent(periodo)}`}>Volver al listado</Link>}
    />
  );
}
