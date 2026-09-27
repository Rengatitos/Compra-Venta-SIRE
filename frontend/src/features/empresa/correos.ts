/** Ancla de la sección de correos en Ajustes: el panel general enlaza aquí. */
export const ANCLA_CORREOS = 'correos';

/** Espejo de `app/domain/empresa.py::CORREO_RE`: forma, no existencia. */
const CORREO_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export const MAX_CORREOS = 10;

export function esCorreoValido(correo: string): boolean {
  return CORREO_RE.test(correo);
}
