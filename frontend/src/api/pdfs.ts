import { descargar, pedir, segmento } from '@/lib/http';
import type { JobAceptado } from '@/types/api';
import type { Libro } from '@/types/domain';

const base = (ruc: string, periodo: string, libro: Libro) =>
  `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/libros/${segmento(libro)}/pdfs`;

/**
 * `POST …/libros/{libro}/pdfs`. Responde `202` con un `job_id`: el scraper
 * entra al portal SOL, busca cada comprobante y guarda su PDF en el servidor.
 *
 * Comparte cola con la extracción de detalle porque la sesión SOL es única por
 * usuario: si hay una en curso, este trabajo espera su turno en vez de
 * pelearse por ella. Un `409` significa que ya hay una descarga de este mismo
 * periodo y libro corriendo. Límite 5/min.
 */
export function iniciarDescargaPdfs(
  ruc: string,
  periodo: string,
  libro: Libro,
): Promise<JobAceptado> {
  return pedir<JobAceptado>(base(ruc, periodo, libro), { metodo: 'POST' });
}

/**
 * Descarga el ZIP de los PDFs ya guardados, con un `manifiesto.csv` que los
 * relaciona con el registro. `404` si todavía no se ha descargado ninguno.
 */
export function descargarZipPdfs(ruc: string, periodo: string, libro: Libro): Promise<void> {
  return descargar(`${base(ruc, periodo, libro)}/zip`, `pdfs_${libro}_${periodo}.zip`);
}
