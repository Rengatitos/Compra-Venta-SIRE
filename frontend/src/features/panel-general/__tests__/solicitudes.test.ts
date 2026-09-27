import { describe, expect, it } from 'vitest';

import { mesActual, periodosEntre, presentarPaso } from '@/features/panel-general/solicitudes';

describe('periodosEntre', () => {
  it('cuenta los meses de un rango, cruzando el año', () => {
    expect(periodosEntre('2025-11', '2026-02')).toEqual([
      '202511',
      '202512',
      '202601',
      '202602',
    ]);
  });

  it('un solo mes y un rango al revés', () => {
    expect(periodosEntre('2026-08', '2026-08')).toEqual(['202608']);
    expect(periodosEntre('2026-09', '2026-08')).toEqual([]);
  });

  it('tiene tope y rechaza lo que no es un mes', () => {
    expect(periodosEntre('2020-01', '2026-12', 5)).toHaveLength(5);
    expect(periodosEntre('', '2026-08')).toEqual([]);
  });
});

describe('mesActual', () => {
  it('da el mes en formato de input month', () => {
    expect(mesActual(new Date(2026, 8, 27))).toBe('2026-09');
  });
});

describe('presentarPaso', () => {
  const base = { paso: 'sire_compras' as const, job_id: 'j', nota: null };

  it('un paso en cola que ya falló dice qué reintento viene', () => {
    const presentacion = presentarPaso({
      ...base,
      estado: 'encolado',
      job_estado: 'pendiente',
      intentos: 1,
      max_intentos: 5,
      siguiente_intento_en: null,
    });
    expect(presentacion).toEqual({ tono: 'aviso', texto: 'Reintento 2 de 5' });
  });

  it('distingue en cola de en curso', () => {
    expect(
      presentarPaso({ ...base, estado: 'encolado', job_estado: 'pendiente', intentos: 0 })
        .texto,
    ).toBe('En cola');
    expect(
      presentarPaso({ ...base, estado: 'encolado', job_estado: 'en_progreso' }).texto,
    ).toBe('En curso');
  });
});
