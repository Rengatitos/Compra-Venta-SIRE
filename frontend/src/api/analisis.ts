import { enviarFormulario, segmento } from '@/lib/http';
import type { ResultadoAnalisis, StatusResponse } from '@/types/api';
import type { Libro } from '@/types/domain';

/**
 * `POST …/libros/{libro}/analisis`. Síncrono y potencialmente lento. Límite 5/min.
 *
 * Es un endpoint multipart aunque no se adjunte nada: el backend declara
 * `archivos: list[UploadFile] = File(default=[])`, así que siempre se envía un
 * FormData. Sin PDFs adjuntos se usa el contexto que la empresa ya tenga
 * indexado en `vector_usuarios`.
 *
 * El libro va en la ruta porque el prompt cambia con él: una venta no es un
 * gasto y su contraparte es un cliente, no un proveedor.
 */
export function ejecutarAnalisis(
  ruc: string,
  periodo: string,
  libro: Libro,
  archivos: readonly File[] = [],
): Promise<StatusResponse<ResultadoAnalisis>> {
  const datos = new FormData();
  for (const archivo of archivos) datos.append('archivos', archivo);

  return enviarFormulario<StatusResponse<ResultadoAnalisis>>(
    `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/libros/${segmento(libro)}/analisis`,
    datos,
  );
}
