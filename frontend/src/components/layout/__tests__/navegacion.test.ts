import { describe, expect, it } from 'vitest';

import { construirNavegacion, subEntradasDePeriodo } from '../navegacion';

describe('construirNavegacion', () => {
  it('siempre ofrece las seis secciones y cada una con su icono', () => {
    const entradas = construirNavegacion(null);

    expect(entradas.map((entrada) => entrada.a)).toEqual([
      '/',
      '/periodos',
      '/externos',
      '/procesos',
      '/plan-cuentas',
      '/ajustes',
    ]);
    expect(entradas.every((entrada) => typeof entrada.icono === 'function')).toBe(true);
  });

  it('sin periodo activo «Periodos» no tiene segundo nivel', () => {
    const periodos = construirNavegacion(null).find((entrada) => entrada.a === '/periodos');

    expect(periodos?.hijos).toBeUndefined();
  });

  it('con periodo activo cuelga sus tres pantallas', () => {
    const periodos = construirNavegacion('202606').find((entrada) => entrada.a === '/periodos');

    expect(periodos?.hijos?.map((hijo) => hijo.a)).toEqual([
      '/periodos/202606',
      '/periodos/202606/auditoria',
      '/periodos/202606/reporte',
    ]);
  });

  it('«Periodos» es exacto: si no, quedaría activo a la vez que su hijo', () => {
    const periodos = construirNavegacion('202606').find((entrada) => entrada.a === '/periodos');

    expect(periodos?.exacto).toBe(true);
  });
});

describe('subEntradasDePeriodo', () => {
  it('el primer hijo es exacto para no quedar activo en auditoría ni reporte', () => {
    const [comprobantes, auditoria, reporte] = subEntradasDePeriodo('202606');

    expect(comprobantes?.exacto).toBe(true);
    expect(auditoria?.exacto).toBeUndefined();
    expect(reporte?.exacto).toBeUndefined();
  });
});
