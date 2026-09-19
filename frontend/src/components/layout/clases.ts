/** Une clases de módulo CSS saltándose las vacías y las condicionales falsas. */
export function clases(...partes: (string | undefined | false)[]): string {
  return partes.filter(Boolean).join(' ');
}
