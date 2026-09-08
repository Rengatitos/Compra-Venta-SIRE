import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import { obtenerJob } from '@/api/jobs';
import { descargarZipPdfs, iniciarDescargaPdfs } from '@/api/pdfs';
import { Button } from '@/components/ui/Button';
import { useJobs } from '@/features/jobs/useJobs';
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
  const { seguir } = useJobs();
  const { mostrar } = useToast();
  const [avance, setAvance] = useState('');
  const descarga = useMutation({
    mutationFn: async () => {
      setAvance('Consultando SUNAT…');
      let aceptado = await iniciarDescargaPdfs(ruc, periodo, libro);
      seguir(aceptado.job_id);
      for (;;) {
        const job = await obtenerJob(aceptado.job_id);
        setAvance(job.progreso.mensaje || 'Esperando turno en SUNAT…');
        if (job.estado === 'fallido')
          throw new Error(job.error || 'SUNAT no pudo completar la descarga.');
        if (job.estado === 'completado') {
          if (
            Number(job.resultado?.pendientes ?? 0) > 0 &&
            Number(job.resultado?.sin_pdf ?? 0) === 0 &&
            Number(job.resultado?.descargados ?? 0) > 0
          ) {
            await new Promise((resolve) => window.setTimeout(resolve, 12000));
            aceptado = await iniciarDescargaPdfs(ruc, periodo, libro);
            seguir(aceptado.job_id);
            continue;
          }
          const faltantes =
            Number(job.resultado?.sin_pdf ?? 0) + Number(job.resultado?.pendientes ?? 0);
          setAvance('Preparando ZIP…');
          await descargarZipPdfs(ruc, periodo, libro);
          mostrar({
            tono: faltantes ? 'neutro' : 'exito',
            titulo: faltantes
              ? 'ZIP descargado con PDFs pendientes'
              : 'ZIP de SUNAT descargado',
            detalle: faltantes
              ? `${faltantes} comprobantes siguen sin PDF. Puedes volver a intentar la descarga. Consulta manifiesto.csv dentro del ZIP.`
              : `PDFs de ${libro} del periodo ${periodo}.`,
          });
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
      }
    },
    onError: (error) =>
      mostrar({
        tono: 'error',
        titulo: 'No se pudo descargar el ZIP de SUNAT',
        detalle: error instanceof Error ? error.message : 'Error inesperado.',
      }),
  });

  return (
    <div>
      <Button
        variante="azul"
        cargando={descarga.isPending}
        onClick={() => descarga.mutate()}
        title={`Descargar todos los PDFs de SUNAT de ${libro} del periodo ${periodo}`}
      >
        {descarga.isPending
          ? 'Descargando PDFs de SUNAT…'
          : 'Descargar comprobantes SUNAT (ZIP)'}
      </Button>
      {descarga.isPending ? <p role="status">{avance} Mantén esta página abierta.</p> : null}
    </div>
  );
}
