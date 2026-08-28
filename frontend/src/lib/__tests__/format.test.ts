import { describe, expect, it } from 'vitest';

import {
  formatearFecha,
  formatearMoneda,
  formatearMontoCompacto,
  formatearPeriodo,
  formatearPorcentaje,
  formatearRuc,
  periodoPorDefecto,
} from '../format';

describe('formatearPeriodo', () => {
  it('convierte YYYYMM en mes y año legibles', () => {
    expect(formatearPeriodo('202606')).toBe('Junio 2026');
    expect(formatearPeriodo('202401')).toBe('Enero 2024');
  });

  it('devuelve la entrada tal cual si no es un periodo válido', () => {
    expect(formatearPeriodo('2026')).toBe('2026');
    expect(formatearPeriodo('202613')).toBe('202613');
  });
});

describe('periodoPorDefecto', () => {
  it('propone el mes anterior, que es el que se suele estar cerrando', () => {
    expect(periodoPorDefecto(new Date('2026-06-15T00:00:00Z'))).toBe('202605');
  });

  it('retrocede de año en enero', () => {
    expect(periodoPorDefecto(new Date('2026-01-04T00:00:00Z'))).toBe('202512');
  });
});

describe('formatearFecha', () => {
  it('acepta null, que es lo que envía el backend sin fecha de emisión', () => {
    expect(formatearFecha(null)).toBe('—');
    expect(formatearFecha(undefined)).toBe('—');
  });

  it('no desplaza el día por zona horaria', () => {
    expect(formatearFecha('2026-06-01')).toBe('01/06/2026');
  });
});

describe('formatearMoneda', () => {
  it('marca los importes ausentes en lugar de imprimir 0', () => {
    expect(formatearMoneda(null)).toBe('—');
  });

  it('formatea soles con dos decimales', () => {
    expect(formatearMoneda(1234.5)).toContain('1,234.50');
  });

  it('no revienta con un código de moneda inválido', () => {
    expect(formatearMoneda(10, 'XX?')).toContain('10.00');
  });
});

describe('formatearMontoCompacto', () => {
  it('abrevia los millones para las métricas del dashboard', () => {
    expect(formatearMontoCompacto(1_250_000)).toBe('S/ 1.25 M');
  });

  it('abrevia los miles desde 10 000', () => {
    expect(formatearMontoCompacto(48_300)).toBe('S/ 48.3 K');
  });

  it('deja los importes pequeños con formato completo', () => {
    expect(formatearMontoCompacto(950)).toContain('950.00');
  });
});

describe('otros formateadores', () => {
  it('redondea porcentajes', () => {
    expect(formatearPorcentaje(66.6)).toBe('67 %');
    expect(formatearPorcentaje(null)).toBe('—');
  });

  it('agrupa el RUC solo si tiene 11 dígitos', () => {
    expect(formatearRuc('20608997106')).toBe('20 608997106');
    expect(formatearRuc('123')).toBe('123');
  });
});
