import { pedir } from '@/lib/http';
import type { TokenResponse } from '@/types/api';

/**
 * `POST /api/v1/auth/google`. Cambia el ID token que devuelve Google Identity
 * Services por el JWT propio de la aplicación.
 *
 * El JWT resultante identifica a una **persona**, no a una empresa: por eso las
 * rutas siguen llevando `/empresas/{ruc}/…` pero ya no hace falta volver a
 * entrar para mirar otra cuenta.
 *
 * `401` si Google rechaza el token, `403` si el correo no está en la lista de
 * autorizados del backend, `503` si Google no responde.
 */
export function iniciarSesionConGoogle(credential: string): Promise<TokenResponse> {
  return pedir<TokenResponse>('/auth/google', { metodo: 'POST', cuerpo: { credential } });
}
