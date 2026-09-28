import { pedir } from '@/lib/http';
import type {
  ConfiguracionCorreo,
  ConfiguracionCorreoUpdate,
  MessageResponse,
  VistaPreviaCorreo,
} from '@/types/api';

/** `GET /api/v1/correos/configuracion`. Solo administradores. */
export function obtenerConfiguracionCorreo(): Promise<ConfiguracionCorreo> {
  return pedir<ConfiguracionCorreo>('/correos/configuracion');
}

/**
 * `PUT /api/v1/correos/configuracion`. Cambios parciales; una contraseña vacía
 * o ausente conserva la guardada.
 */
export function guardarConfiguracionCorreo(
  datos: ConfiguracionCorreoUpdate,
): Promise<ConfiguracionCorreo> {
  return pedir<ConfiguracionCorreo>('/correos/configuracion', { metodo: 'PUT', cuerpo: datos });
}

/** Cómo queda la plantilla con datos de ejemplo. No guarda nada. */
export function previsualizarCorreo(
  plantilla_asunto: string,
  plantilla_cuerpo: string,
): Promise<VistaPreviaCorreo> {
  return pedir<VistaPreviaCorreo>('/correos/configuracion/vista-previa', {
    metodo: 'POST',
    cuerpo: { plantilla_asunto, plantilla_cuerpo },
  });
}

/** Correo de prueba con la configuración guardada (no la del formulario). */
export function enviarCorreoPrueba(destinatario: string): Promise<MessageResponse> {
  return pedir<MessageResponse>('/correos/configuracion/prueba', {
    metodo: 'POST',
    cuerpo: { destinatario },
  });
}
