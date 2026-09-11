import { describe, expect, it } from 'vitest';

import { formatearMoneda } from '../format';
import { formatearImporteComprobante } from '../importesComprobante';

describe('importes SIRE en la moneda del comprobante', () => {
  it.each([
    [157732, 3.356, 47000],
    [171156, 3.356, 51000],
    [149600, 3.4, 44000],
    [299200, 3.4, 88000],
    [60.408, 3.356, 18],
    [-157732, 3.356, -47000],
  ])('convierte %s PEN con TC %s a %s USD', (importe, tasa, esperado) => {
    expect(
      formatearImporteComprobante(importe, {
        origen: 'sire',
        moneda: 'USD',
        tipo_cambio: tasa,
      }),
    ).toBe(formatearMoneda(esperado, 'USD'));
  });

  it('conserva los importes en soles', () => {
    expect(
      formatearImporteComprobante(118, {
        origen: 'sire',
        moneda: 'PEN',
        tipo_cambio: 3.356,
      }),
    ).toBe(formatearMoneda(118, 'PEN'));
  });

  it('no convierte otros orígenes que ya están en moneda original', () => {
    expect(
      formatearImporteComprobante(47000, {
        origen: 'manual',
        moneda: 'USD',
        tipo_cambio: 3.356,
      }),
    ).toBe(formatearMoneda(47000, 'USD'));
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])(
    'sin tipo de cambio válido (%s) muestra PEN',
    (tasa) => {
      expect(
        formatearImporteComprobante(157732, {
          origen: 'sire',
          moneda: 'USD',
          tipo_cambio: tasa,
        }),
      ).toBe(formatearMoneda(157732, 'PEN'));
    },
  );
});
