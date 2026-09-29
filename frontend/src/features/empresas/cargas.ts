import type { CargaResumen } from '@/types/api';

/** «Carga masiva · archivo.xlsx» o «Alta individual». */
export function describirCarga(carga: CargaResumen): string {
  return carga.modalidad === 'masiva'
    ? `Carga masiva${carga.archivo ? ` · ${carga.archivo}` : ''}`
    : 'Alta individual';
}
