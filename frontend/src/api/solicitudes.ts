import { descargar, pedir, segmento } from '@/lib/http';
import type { EnvioListado, SolicitudCreate, SolicitudResponse } from '@/types/api';

const base = (id: string) => `/solicitudes/${segmento(id)}`;

/**
 * `POST /api/v1/solicitudes`. Encola, por cada empresa y periodo, la descarga
 * SIRE, los comprobantes y la clasificación con IA; al terminar todo se arma
 * el ZIP y se envía por correo. Sigue en el servidor aunque se cierre la página.
 */
export function crearSolicitud(datos: SolicitudCreate): Promise<SolicitudResponse> {
  return pedir<SolicitudResponse>('/solicitudes', { metodo: 'POST', cuerpo: datos });
}

/** `GET /api/v1/solicitudes`: las más recientes, sin el estado vivo de cada paso. */
export function listarSolicitudes(): Promise<SolicitudResponse[]> {
  return pedir<SolicitudResponse[]>('/solicitudes');
}

/** `GET /api/v1/solicitudes/{id}`: con intentos y próximo reintento de cada paso. */
export function obtenerSolicitud(id: string): Promise<SolicitudResponse> {
  return pedir<SolicitudResponse>(base(id));
}

/** `POST /api/v1/solicitudes/{id}/reintentar`: vuelve a encolar lo que falló. */
export function reintentarSolicitud(id: string): Promise<SolicitudResponse> {
  return pedir<SolicitudResponse>(`${base(id)}/reintentar`, { metodo: 'POST' });
}

export function descargarZipSolicitud(id: string): Promise<void> {
  return descargar(`${base(id)}/zip`, 'descarga.zip');
}

/** `GET /api/v1/correos/envios`: a quién se enviaron los resultados y cómo acabó. */
export function listarEnvios(): Promise<EnvioListado[]> {
  return pedir<EnvioListado[]>('/correos/envios');
}
