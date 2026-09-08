import { useMutation } from '@tanstack/react-query';

import { descargarZipPdfs } from '@/api/pdfs';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/hooks/useToast';
import { ApiError } from '@/lib/http';
import type { Libro } from '@/types/domain';

/**
 * Baja el ZIP con los PDFs que ya están guardados en el servidor.
 *
 * Ya no entra al portal SOL: los PDFs se descargan dentro de «Completar con
 * GLOSA», en la misma pasada que extrae el detalle de cada comprobante. Este
 * botón sólo empaqueta lo que esa pasada dejó en disco, junto con el
 * `manifiesto.csv` que lo cruza con el registro.
 */
export function DescargarPdfsButton({
  ruc,
  periodo,
  libro,
}: {
  ruc: string;
  periodo: string;
  libro: Libro;
}) {
  const { mostrar } = useToast();
  const descarga = useMutation({
    mutationFn: () => descargarZipPdfs(ruc, periodo, libro),
    onError: (fallo) => {
      const vacio = fallo instanceof ApiError && fallo.esNoEncontrado;
      mostrar({
        tono: vacio ? 'neutro' : 'error',
        titulo: vacio ? 'Todavía no hay PDFs guardados' : 'No se pudo descargar el ZIP',
        detalle: vacio
          ? `Ejecuta «Completar con GLOSA» sobre ${libro}: descarga el PDF de cada comprobante junto con su detalle.`
          : fallo instanceof Error
            ? fallo.message
            : 'Error inesperado.',
      });
    },
  });

  return (
    <Button
      cargando={descarga.isPending}
      onClick={() => descarga.mutate()}
      title={`ZIP con los PDFs de SUNAT de ${libro} del periodo ${periodo} y su manifiesto`}
    >
      ZIP de PDFs SUNAT
    </Button>
  );
}
