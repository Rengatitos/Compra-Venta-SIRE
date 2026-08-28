import { describe, expect, it } from 'vitest';

import { esPeriodoValido, esRucValido, LIBROS_IMPLEMENTADOS } from '../domain';

describe('esPeriodoValido', () => {
  it('acepta el formato YYYYMM del backend', () => {
    expect(esPeriodoValido('202606')).toBe(true);
    expect(esPeriodoValido('202612')).toBe(true);
  });

  it('rechaza meses fuera de rango y longitudes distintas', () => {
    expect(esPeriodoValido('202600')).toBe(false);
    expect(esPeriodoValido('202613')).toBe(false);
    expect(esPeriodoValido('20260')).toBe(false);
    expect(esPeriodoValido('')).toBe(false);
  });
});

describe('esRucValido', () => {
  it('exige exactamente 11 dígitos', () => {
    expect(esRucValido('20608997106')).toBe(true);
    expect(esRucValido(' 20608997106 ')).toBe(true);
    expect(esRucValido('2060899710')).toBe(false);
    expect(esRucValido('2060899710a')).toBe(false);
  });
});

describe('libros', () => {
  it('solo declara compras como implementado, porque ventas responde 501', () => {
    expect(LIBROS_IMPLEMENTADOS).toEqual(['compras']);
  });
});
