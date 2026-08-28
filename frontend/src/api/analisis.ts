import { enviarFormulario, segmento } from '@/lib/http';
import type { ResultadoAnalisis, StatusResponse } from '@/types/api';

/**
 * `POST …/analisis`. Síncrono y potencialmente lento. Límite 5/min.
 *
 * Es un endpoint multipart aunque no se adjunte nada: el backend declara
 * `archivos: list[UploadFile] = File(default=[])`, así que siempre se envía un
 * FormData. Sin PDFs adjuntos se usa el contexto que la empresa ya tenga
 * indexado en `vector_usuarios`.
 */
export function ejecutarAnalisis(
  ruc: string,
  periodo: string,
  archivos: readonly File[] = [],
): Promise<StatusResponse<ResultadoAnalisis>> {
  const datos = new FormData();
  for (const archivo of archivos) datos.append('archivos', archivo);

  return enviarFormulario<StatusResponse<ResultadoAnalisis>>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/analisis`,
    datos,
  );
}
