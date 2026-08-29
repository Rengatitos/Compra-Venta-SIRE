import { describe, expect, it } from 'vitest';

import {
  aNumero,
  limpiarDescripcion,
  normalizarDetalleSunat,
} from '../detalleSunat';

/** Fila real del portal SOL, con la basura que trae la celda de descripción. */
const FILA_REAL = {
  cantidad: '0.50',
  unidad_medida: 'UNIDAD',
  codigo: '0100',
  descripcion: 'COCA COLA VR 1.5L X08 RF@#@      -4    @#@33.34@#@.00@#@.00@#@.00@#@16.67',
  valor_unitario: '33.34',
  precio_unitario: '33.34',
  valor_venta: '16.67',
  icbper: '0.00',
};

describe('limpiarDescripcion', () => {
  it('corta la copia de las columnas numéricas que SUNAT pega en la celda', () => {
    expect(limpiarDescripcion(FILA_REAL.descripcion)).toBe('COCA COLA VR 1.5L X08 RF');
  });

  it('colapsa los espacios sobrantes del portal', () => {
    expect(limpiarDescripcion('  INCA  KOLA   VR 1.5L  ')).toBe('INCA KOLA VR 1.5L');
  });

  it('tolera una descripción sin separador y lo que no sea texto', () => {
    expect(limpiarDescripcion('AGUA SAN LUIS 625ML')).toBe('AGUA SAN LUIS 625ML');
    expect(limpiarDescripcion(null)).toBe('');
  });
});

describe('aNumero', () => {
  it('lee los formatos que trae el popup', () => {
    expect(aNumero('0.50')).toBe(0.5);
    expect(aNumero('.00')).toBe(0);
    expect(aNumero('1,234.56')).toBe(1234.56);
    expect(aNumero(42)).toBe(42);
  });

  it('distingue un importe ausente de un cero', () => {
    expect(aNumero('')).toBeNull();
    expect(aNumero('   ')).toBeNull();
    expect(aNumero('no es un número')).toBeNull();
    expect(aNumero(undefined)).toBeNull();
    expect(aNumero('0')).toBe(0);
  });
});

describe('normalizarDetalleSunat', () => {
  it('convierte la fila del portal en algo que la tabla puede pintar', () => {
    const { items } = normalizarDetalleSunat([FILA_REAL]);

    expect(items).toHaveLength(1);
    expect(items[0]).toEqual({
      indice: 0,
      codigo: '0100',
      descripcion: 'COCA COLA VR 1.5L X08 RF',
      unidadMedida: 'UNIDAD',
      cantidad: 0.5,
      valorUnitario: 33.34,
      precioUnitario: 33.34,
      valorVenta: 16.67,
      icbper: 0,
    });
  });

  it('suma los importes de la corrida', () => {
    const resultado = normalizarDetalleSunat([
      FILA_REAL,
      { ...FILA_REAL, codigo: '0098', valor_venta: '10.00', icbper: '0.50' },
    ]);

    expect(resultado.totalValorVenta).toBeCloseTo(26.67, 2);
    expect(resultado.totalIcbper).toBeCloseTo(0.5, 2);
  });

  it('cuenta las filas que no sirven en vez de fingir que no llegaron', () => {
    const resultado = normalizarDetalleSunat([
      FILA_REAL,
      'una cadena suelta',
      null,
      { descripcion: '', codigo: '   ' },
    ]);

    expect(resultado.items).toHaveLength(1);
    expect(resultado.descartadas).toBe(3);
  });

  it('conserva el índice original como clave de fila', () => {
    const { items } = normalizarDetalleSunat([null, FILA_REAL]);
    expect(items[0]?.indice).toBe(1);
  });
});
