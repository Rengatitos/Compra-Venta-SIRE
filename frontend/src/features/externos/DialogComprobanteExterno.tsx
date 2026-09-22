import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import { descargarImagenExterna } from '@/api/comprobantesExternos';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { WarningState } from '@/components/ui/Feedback';
import {
  formatearFecha,
  formatearFechaHora,
  formatearMoneda,
  formatearPorcentaje,
} from '@/lib/format';
import layout from '@/styles/layouts.module.css';
import type { ComprobanteExternoResponse } from '@/types/api';

import estilos from './ExternosPage.module.css';
import { identificador, nombreCampo, presentarFuente } from './fuenteExterna';

interface Props {
  ruc: string;
  comprobante: ComprobanteExternoResponse | null;
  onCerrar: () => void;
}

/** La foto va con el Bearer: se pide como blob y se muestra por object URL. */
function useFoto(ruc: string, comprobante: ComprobanteExternoResponse | null) {
  const id = comprobante?.tiene_imagen ? comprobante.id : null;
  const consulta = useQuery({
    queryKey: ['comprobante-externo-imagen', ruc, id],
    queryFn: ({ signal }) => descargarImagenExterna(ruc, id ?? '', signal),
    enabled: id !== null,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });

  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!consulta.data) {
      setUrl(null);
      return;
    }
    const creada = URL.createObjectURL(consulta.data);
    setUrl(creada);
    return () => URL.revokeObjectURL(creada);
  }, [consulta.data]);

  return { url, error: consulta.isError };
}

interface PropsDato {
  termino: string;
  children: ReactNode;
  numerico?: boolean;
}

function Dato({ termino, children, numerico = false }: PropsDato) {
  return (
    <div>
      <dt className={layout.termino}>{termino}</dt>
      <dd className={`${layout.descripcion} ${numerico ? (layout.numerica ?? '') : ''}`}>
        {children}
      </dd>
    </div>
  );
}

export function DialogComprobanteExterno({ ruc, comprobante, onCerrar }: Props) {
  const foto = useFoto(ruc, comprobante);
  const fuente = comprobante ? presentarFuente(comprobante.fuente) : null;

  return (
    <Dialog
      abierto={comprobante !== null}
      titulo={
        comprobante ? `${fuente?.texto ?? ''} ${identificador(comprobante)}` : 'Comprobante'
      }
      onCerrar={onCerrar}
      ancho="amplio"
      acciones={
        <Button variante="primario" onClick={onCerrar}>
          Cerrar
        </Button>
      }
    >
      {comprobante ? (
        <div className={estilos.detalle}>
          {foto.url ? (
            <img
              className={estilos.foto}
              src={foto.url}
              alt="Foto del comprobante enviada desde Apaclla Bot"
            />
          ) : (
            <p className={estilos.sinFoto}>
              {!comprobante.tiene_imagen
                ? 'El bot no envió la foto de este comprobante.'
                : foto.error
                  ? 'No se pudo cargar la foto.'
                  : 'Cargando la foto…'}
            </p>
          )}

          <div className={layout.pila}>
            <div className={estilos.insignias}>
              <Badge tono={fuente?.tono ?? 'neutro'}>{fuente?.texto}</Badge>
              <Badge tono="exito" conPunto>
                Recibido desde el bot
              </Badge>
            </div>

            {comprobante.campos_dudosos.length > 0 ? (
              <WarningState
                titulo="El bot no estaba seguro de algunos datos"
                texto={`Revisa ${comprobante.campos_dudosos.map(nombreCampo).join(', ')}. La persona los confirmó antes de enviarlos.`}
              />
            ) : null}

            <dl className={layout.definiciones}>
              <Dato termino="Total" numerico>
                {formatearMoneda(Number(comprobante.total), comprobante.moneda)}
              </Dato>
              <Dato termino="Fecha">
                {formatearFecha(comprobante.fecha_operacion)}
                {comprobante.hora_operacion ? `, ${comprobante.hora_operacion}` : ''}
              </Dato>
              <Dato termino="Libro">
                {comprobante.libro === 'ventas' ? 'Ventas' : 'Compras'}
              </Dato>
              <Dato termino="Tipo">
                {comprobante.tipo_cp} {comprobante.tipo_cp_descripcion}
              </Dato>
              <Dato termino={comprobante.libro === 'ventas' ? 'Cliente' : 'Proveedor'}>
                {comprobante.contraparte.nombre || '—'}
                {comprobante.contraparte.documento
                  ? ` (${comprobante.contraparte.documento})`
                  : ''}
              </Dato>
              {comprobante.igv ? (
                <Dato termino="IGV" numerico>
                  {formatearMoneda(Number(comprobante.igv), comprobante.moneda)}
                </Dato>
              ) : null}
              <Dato termino="Detalle">{comprobante.descripcion || '—'}</Dato>
              <Dato termino="Confianza de la lectura">
                {formatearPorcentaje(
                  comprobante.confianza === null ? null : comprobante.confianza * 100,
                )}
              </Dato>
              <Dato termino="Enviado desde el bot">
                {formatearFechaHora(comprobante.enviado_en)}
              </Dato>
            </dl>
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}
