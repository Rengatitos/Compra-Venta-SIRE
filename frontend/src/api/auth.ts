import { pedir } from '@/lib/http';
import type { EmpresaLogin, TokenResponse } from '@/types/api';

/** `POST /api/v1/auth/login`. Devuelve el JWT que identifica a la empresa. */
export function login(credenciales: EmpresaLogin): Promise<TokenResponse> {
  return pedir<TokenResponse>('/auth/login', { metodo: 'POST', cuerpo: credenciales });
}
