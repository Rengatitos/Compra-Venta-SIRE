import { descargar, pedir, segmento } from '@/lib/http';
import type { JobAceptado } from '@/types/api';

const base = (ruc: string, periodo: string) =>
  `/empresas/${segmento(ruc)}/periodos/${segmento(periodo)}/detracciones`;

export interface NpdPeriodo {
  pdf_ruta?: string;
  error_pdf?: string;
  numero: string;
  cabecera: {
    fecRegistro?: string;
    fecCreacion?: string;
    fecLimitePago?: string;
    importe?: number;
    estado?: string;
    desRazonSocial?: string;
  };
  detalle: Record<string, unknown>;
}

export function listarNpds(
  ruc: string,
  periodo: string,
): Promise<{ npds: NpdPeriodo[]; consultado_en: string | null }> {
  return pedir(`${base(ruc, periodo)}/npds`);
}

export function descargarPdfNpd(ruc: string, periodo: string, numero: string): Promise<void> {
  return descargar(`${base(ruc, periodo)}/npds/${segmento(numero)}/pdf`, `npd_${numero}.pdf`);
}

export function consultarDetracciones(ruc: string, periodo: string): Promise<JobAceptado> {
  return pedir<JobAceptado>(base(ruc, periodo), { metodo: 'POST' });
}

export function disponibilidadDetracciones(
  ruc: string,
  periodo: string,
): Promise<{ disponible: boolean }> {
  return pedir<{ disponible: boolean }>(`${base(ruc, periodo)}/disponibilidad`);
}

export function descargarDetracciones(ruc: string, periodo: string): Promise<void> {
  return descargar(`${base(ruc, periodo)}/zip`, `detracciones_${periodo}.zip`);
}
