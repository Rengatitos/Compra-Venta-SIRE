import { pedir, segmento } from '@/lib/http';
import type { CuentaApi, CuentaApiConClave } from '@/types/api';

/** Cuentas de API (integraciones). Todo solo para administradores. */
export function listarCuentasApi(): Promise<CuentaApi[]> {
  return pedir<CuentaApi[]>('/cuentas-api');
}

/**
 * Devuelve la contraseña una sola vez. `409` si el correo ya existe. La cuenta
 * tiene acceso completo a la API.
 */
export function crearCuentaApi(email: string, vigenciaDias: number): Promise<CuentaApiConClave> {
  return pedir<CuentaApiConClave>('/cuentas-api', {
    metodo: 'POST',
    cuerpo: { email, vigencia_dias: vigenciaDias },
  });
}

/** Contraseña nueva; la anterior deja de servir en el acto. */
export function regenerarCuentaApi(email: string): Promise<CuentaApiConClave> {
  return pedir<CuentaApiConClave>(`/cuentas-api/${segmento(email)}/regenerar`, {
    metodo: 'POST',
    cuerpo: {},
  });
}

export function eliminarCuentaApi(email: string): Promise<void> {
  return pedir<void>(`/cuentas-api/${segmento(email)}`, { metodo: 'DELETE' });
}
