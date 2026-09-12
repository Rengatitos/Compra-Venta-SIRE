import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import { descargarZipSunatCompleto } from '@/api/pdfs';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/hooks/useToast';
import type { Libro } from '@/types/domain';

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
  const [avance, setAvance] = useState('');
  const descarga = useMutation({
    mutationFn: () => descargarZipSunatCompleto(ruc, periodo, libro, setAvance),
    onSuccess: (faltantes) => {
      mostrar({
        tono: faltantes ? 'neutro' : 'exito',
        titulo: faltantes
          ? 'ZIP descargado con comprobantes faltantes'
          : 'ZIP de compras y ventas descargado',
        detalle: faltantes
          ? `SUNAT no entregó ${faltantes} PDFs. Consulta faltantes.csv dentro del ZIP.`
          : 'Incluye los PDFs obtenidos desde SUNAT de ambos registros.',
      });
    },
    onError: (fallo) => {
      mostrar({
        tono: 'error',
        titulo: 'No se pudo descargar el ZIP',
        detalle: fallo instanceof Error ? fallo.message : 'Error inesperado.',
      });
    },
  });

  return (
    <>
      <Button
        cargando={descarga.isPending}
        onClick={() => descarga.mutate()}
        title={`Descargar desde SUNAT los PDFs de compras y ventas del periodo ${periodo}`}
      >
        ZIP de PDFs SUNAT
      </Button>
      {descarga.isPending && (
        <span role="status">{avance || 'Iniciando descarga desde SUNAT…'}</span>
      )}
    </>
  );
}
