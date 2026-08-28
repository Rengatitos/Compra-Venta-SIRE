import { pedir, segmento } from '@/lib/http';
import type { MessageResponse, PeriodoResponse } from '@/types/api';

const base = (ruc: string) => `/empresas/${segmento(ruc)}/periodos`;

export function listarPeriodos(ruc: string): Promise<PeriodoResponse[]> {
  return pedir<PeriodoResponse[]>(base(ruc));
}

/** `409` si el periodo ya existe para esa empresa. */
export function crearPeriodo(ruc: string, periodo: string): Promise<PeriodoResponse> {
  return pedir<PeriodoResponse>(base(ruc), { metodo: 'POST', cuerpo: { periodo } });
}

export function obtenerPeriodo(ruc: string, periodo: string): Promise<PeriodoResponse> {
  return pedir<PeriodoResponse>(`${base(ruc)}/${segmento(periodo)}`);
}

export function actualizarEstadoPeriodo(
  ruc: string,
  periodo: string,
  estado: string,
): Promise<PeriodoResponse> {
  return pedir<PeriodoResponse>(`${base(ruc)}/${segmento(periodo)}`, {
    metodo: 'PUT',
    cuerpo: { estado },
  });
}

/** Borra también todos los comprobantes del periodo. */
export function eliminarPeriodo(ruc: string, periodo: string): Promise<MessageResponse> {
  return pedir<MessageResponse>(`${base(ruc)}/${segmento(periodo)}`, { metodo: 'DELETE' });
}
