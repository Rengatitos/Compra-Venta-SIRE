import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { exportarComprobante, obtenerComprobante } from '@/api/comprobantes';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { ErrorState, Skeleton } from '@/components/ui/Feedback';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import type { FormatoExport } from '@/types/domain';

import { ComprobanteNoEncontrado, FichaComprobante } from './FichaComprobante';

interface Props {
  ruc: string;
  periodo: string;
  /** `null` con el modal cerrado. Sale del parámetro `?comprobante=` de la URL. */
  serieNumero: string | null;
  onCerrar: () => void;
}

export function DialogComprobante({ ruc, periodo, serieNumero, onCerrar }: Props) {
  const { mostrar } = useToast();
  const [exportando, setExportando] = useState<FormatoExport | null>(null);

  const comprobante = useQuery({
    queryKey: ['comprobante', ruc, periodo, serieNumero],
    queryFn: () => obtenerComprobante(ruc, periodo, serieNumero as string),
    enabled: serieNumero !== null,
  });

  const datos = comprobante.data;

  async function exportar(formato: FormatoExport) {
    if (!serieNumero) return;
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

  const noEncontrado =
    comprobante.error instanceof ApiError && comprobante.error.esNoEncontrado;

  return (
    <Dialog
      abierto={serieNumero !== null}
      ancho="amplio"
      titulo={serieNumero ?? ''}
      texto={
        datos ? `${datos.tipo_cp_descripcion} · ${datos.razon_social || 's/n'}` : undefined
      }
      onCerrar={onCerrar}
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
          <Button variante="primario" onClick={onCerrar}>
            Cerrar
          </Button>
        </>
      }
    >
      {comprobante.isPending ? <Skeleton lineas={6} etiqueta="Cargando comprobante" /> : null}

      {comprobante.isError ? (
        noEncontrado ? (
          <ComprobanteNoEncontrado periodo={periodo} />
        ) : (
          <ErrorState
            titulo="No se pudo cargar el comprobante"
            texto={
              comprobante.error instanceof ApiError
                ? comprobante.error.message
                : 'Error inesperado.'
            }
            accion={
              <Button pequeno onClick={() => void comprobante.refetch()}>
                Reintentar
              </Button>
            }
          />
        )
      ) : null}

      {datos ? <FichaComprobante datos={datos} ruc={ruc} periodo={periodo} /> : null}
    </Dialog>
  );
}
