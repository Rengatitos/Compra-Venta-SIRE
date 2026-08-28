import { enviarFormulario, pedir, segmento } from '@/lib/http';
import type {
  DataResponse,
  FileListResponse,
  ResultadoReferencia,
  StatusResponse,
  TemasResponse,
} from '@/types/api';

const base = (ruc: string) => `/empresas/${segmento(ruc)}/referencias`;

export interface ChunkVectorial {
  texto?: string;
  metadata?: { documento?: string; pagina?: number };
}

export function listarReferencias(ruc: string): Promise<FileListResponse> {
  return pedir<FileListResponse>(base(ruc));
}

/**
 * Sube un PDF y lo indexa (chunks por página + embeddings). Si el PDF no tiene
 * texto extraíble el backend responde `estado: "advertencia"`, no un error.
 */
export function subirReferencia(
  ruc: string,
  archivo: File,
): Promise<StatusResponse<ResultadoReferencia>> {
  const datos = new FormData();
  datos.append('archivo', archivo);
  return enviarFormulario<StatusResponse<ResultadoReferencia>>(base(ruc), datos);
}

export function eliminarReferencia(ruc: string, nombre: string): Promise<StatusResponse> {
  return pedir<StatusResponse>(`${base(ruc)}/${segmento(nombre)}`, { metodo: 'DELETE' });
}

/** Documentos del vector global, compartido entre todas las empresas. */
export function obtenerTemasBase(ruc: string): Promise<TemasResponse> {
  return pedir<TemasResponse>(`${base(ruc)}/temas-base`);
}

export function obtenerChunks(ruc: string): Promise<DataResponse<ChunkVectorial[]>> {
  return pedir<DataResponse<ChunkVectorial[]>>(`${base(ruc)}/datos`);
}
