import { pedir, segmento } from '@/lib/http';
import type {
  EmpresaCreate,
  EmpresaResponse,
  EmpresaUpdate,
  MessageResponse,
  StatusResponse,
} from '@/types/api';

const base = (ruc: string) => `/empresas/${segmento(ruc)}`;

/** `POST /api/v1/empresas`. Alta de empresa, sin autenticación. Límite 5/min. */
export function crearEmpresa(datos: EmpresaCreate): Promise<EmpresaResponse> {
  return pedir<EmpresaResponse>('/empresas', { metodo: 'POST', cuerpo: datos });
}

export function obtenerEmpresa(ruc: string): Promise<EmpresaResponse> {
  return pedir<EmpresaResponse>(base(ruc));
}

/**
 * `PUT /api/v1/empresas/{ruc}`. Solo se envían las claves con valor: para el
 * backend, un `sunat_client_id` vacío significa "no lo toques", no "bórralo".
 */
export function actualizarEmpresa(ruc: string, datos: EmpresaUpdate): Promise<EmpresaResponse> {
  const cuerpo: EmpresaUpdate = {};
  for (const [clave, valor] of Object.entries(datos)) {
    if (typeof valor === 'string' && valor.trim() !== '') {
      cuerpo[clave as keyof EmpresaUpdate] = valor.trim();
    }
  }
  return pedir<EmpresaResponse>(base(ruc), { metodo: 'PUT', cuerpo });
}

/** Borra en cascada comprobantes, periodos y chunks vectoriales. */
export function eliminarEmpresa(ruc: string): Promise<MessageResponse> {
  return pedir<MessageResponse>(base(ruc), { metodo: 'DELETE' });
}

/** `POST …/token-sunat`. Fuerza un OAuth nuevo contra la API SIRE. */
export function renovarTokenSunat(ruc: string): Promise<StatusResponse> {
  return pedir<StatusResponse>(`${base(ruc)}/token-sunat`, { metodo: 'POST' });
}
