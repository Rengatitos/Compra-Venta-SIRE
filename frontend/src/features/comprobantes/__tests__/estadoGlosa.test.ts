import { describe, expect, it } from 'vitest';

import { ESTADOS_GLOSA } from '@/types/domain';

import { presentarEstadoGlosa } from '../estadoGlosa';

describe('estado de la glosa', () => {
  it('cada estado tiene rótulo propio y un tono distinto', () => {
    expect(presentarEstadoGlosa('con_glosa')).toEqual({ tono: 'exito', texto: 'Con glosa' });
    expect(presentarEstadoGlosa('sin_glosa')).toEqual({ tono: 'aviso', texto: 'Sin glosa' });
    expect(presentarEstadoGlosa('en_evaluacion')).toEqual({
      tono: 'info',
      texto: 'En evaluación',
    });
    expect(presentarEstadoGlosa('pendiente')).toEqual({ tono: 'neutro', texto: 'Pendiente' });
  });

  it('cubre todos los estados que declara el dominio', () => {
    const textos = new Set(ESTADOS_GLOSA.map((estado) => presentarEstadoGlosa(estado).texto));
    expect(textos.size).toBe(ESTADOS_GLOSA.length);
    // Ninguno cae al rótulo crudo de respaldo.
    for (const estado of ESTADOS_GLOSA) {
      expect(presentarEstadoGlosa(estado).texto).not.toBe(estado);
    }
  });

  it('un estado que el backend añada después no rompe la pantalla', () => {
    expect(presentarEstadoGlosa('algo_nuevo')).toEqual({ tono: 'neutro', texto: 'algo_nuevo' });
  });
});
