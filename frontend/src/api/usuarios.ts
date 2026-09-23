import { pedir, segmento } from '@/lib/http';
import type { RolUsuario, UsuarioAcceso, UsuarioResponse } from '@/types/api';

/** `GET /auth/yo`. Correo y rol de la sesión; el rol puede cambiar con la sesión abierta. */
export function obtenerYo(): Promise<UsuarioResponse> {
  return pedir<UsuarioResponse>('/auth/yo');
}

/** Solo administradores (`403` para el resto). */
export function listarUsuarios(): Promise<UsuarioAcceso[]> {
  return pedir<UsuarioAcceso[]>('/usuarios');
}

/** `409` si ya tiene acceso o es un administrador fijo. */
export function agregarUsuario(email: string, rol: RolUsuario): Promise<UsuarioAcceso> {
  return pedir<UsuarioAcceso>('/usuarios', { metodo: 'POST', cuerpo: { email, rol } });
}

export function cambiarRol(email: string, rol: RolUsuario): Promise<UsuarioAcceso> {
  return pedir<UsuarioAcceso>(`/usuarios/${segmento(email)}`, {
    metodo: 'PATCH',
    cuerpo: { rol },
  });
}

export function quitarUsuario(email: string): Promise<void> {
  return pedir<void>(`/usuarios/${segmento(email)}`, { metodo: 'DELETE' });
}
