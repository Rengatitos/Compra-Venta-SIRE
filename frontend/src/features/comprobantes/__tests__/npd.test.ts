import { describe, expect, it } from 'vitest';

import type { NpdPeriodo } from '@/api/detracciones';

import { normalizarNpd, presentarEstadoNpd, soloFecha } from '../npd';

/** Copia de un NPD real del periodo 202607, con las claves tal cual las guarda SUNAT. */
const npd: NpdPeriodo = {
  numero: '0001956903471',
  cabecera: {
    fecRegistro: '06/07/2026 09:46:41',
    estado: 'No Vigente',
    numRuc: '20610202251',
    razonSocial: 'razon social',
    numNpd: '0001956903471',
    desRazonSocial: 'CORPORACION UNICACHI KRYSTAL S.A.C.          ',
    fecCreacion: '06/07/2026',
    fecLimitePago: '10/07/2026',
    indicadorEstado: '11',
    importe: 270,
  } as NpdPeriodo['cabecera'],
  detalle: {
    cabecera: {
      'Número de Pago de Detracciones - NPD': '0001956903471',
      'RUC del que generó el NPD': '20610202251',
      'Nombre o Razón Social del que generó el NPD': 'CORPORACION UNICACHI KRYSTAL S.A.C.',
      'Fecha y hora de generación del NPD': '06/07/2026 09:46',
      'Fecha límite de Pago': '10/07/2026',
      'Monto del NPD': 'S/ 270.00',
      'Estado del NPD': 'No Vigente',
    },
    depositos: [
      {
        'N° de cuenta de detracciones': '00048189555',
        'RUC del Proveedor': '20609779943',
        'Nombre o Razón Social del Proveedor': 'CORPORACION MEGA PANELES E.I.R.L.',
        'Serie y Número de Comprobante': 'E001 00000772',
        'Monto de Depósito S/': '270.00',
      },
    ],
  },
};

it('arma el resumen con el RUC y la razón social útiles', () => {
  const datos = normalizarNpd(npd);
  expect(datos.numero).toBe('0001956903471');
  expect(datos.importe).toBe(270);
  expect(datos.generadoPor).toBe('20610202251 · CORPORACION UNICACHI KRYSTAL S.A.C.');
  expect(datos.estado).toEqual({ tono: 'neutro', texto: 'No vigente' });
  expect(datos.registro).toBe('06/07/2026 09:46:41');
  expect(datos.vencimiento).toBe('10/07/2026');
});

it('no repite debajo lo que el resumen ya dice', () => {
  // La página del NPD es un calco del listado con otros rótulos: no queda nada.
  expect(normalizarNpd(npd).datosPortal).toEqual([]);
});

it('deja los datos del portal que el resumen no cubre', () => {
  const datos = normalizarNpd({
    ...npd,
    detalle: { cabecera: { 'Tipo de bien o servicio': '019 - Otros servicios' } },
  });
  expect(datos.datosPortal).toEqual([
    {
      clave: 'Tipo de bien o servicio',
      etiqueta: 'Tipo de bien o servicio',
      valor: '019 - Otros servicios',
    },
  ]);
});

it('encabeza cada depósito con su comprobante y su monto', () => {
  const deposito = normalizarNpd(npd).depositos[0];
  expect(deposito?.titulo).toBe('E001 00000772');
  expect(deposito?.monto).toBe('S/ 270.00');
  // Ni la serie ni el monto se repiten abajo, y el adquiriente es la propia
  // empresa, que ya sale en el resumen.
  expect(deposito?.campos).toEqual([
    { clave: 'N° de cuenta de detracciones', etiqueta: 'Cuenta', valor: '00048189555' },
    { clave: 'RUC del Proveedor', etiqueta: 'RUC proveedor', valor: '20609779943' },
    {
      clave: 'Nombre o Razón Social del Proveedor',
      etiqueta: 'Proveedor',
      valor: 'CORPORACION MEGA PANELES E.I.R.L.',
    },
  ]);
});

it('numera el depósito que llega sin comprobante', () => {
  const datos = normalizarNpd({
    ...npd,
    detalle: { depositos: [{ 'Tipo de bien o servicio': '019' }] },
  });
  expect(datos.depositos[0]?.titulo).toBe('Depósito 1');
  expect(datos.depositos[0]?.monto).toBe('');
});

it('deja fuera el relleno del listado y conserva el resto', () => {
  const datos = normalizarNpd(npd);
  const otros = Object.fromEntries(
    datos.otrosListado.map((dato) => [dato.etiqueta, dato.valor]),
  );
  // `razonSocial` llega con el nombre de la columna como valor: es ruido.
  expect(otros).toEqual({ 'Indicador de estado': '11' });
  expect(datos.restoDetalle).toEqual({});
});

it('nunca pierde un detalle con forma inesperada', () => {
  const datos = normalizarNpd({
    numero: '000123',
    cabecera: {},
    detalle: { concepto: 'Arrendamiento' },
  });
  expect(datos.restoDetalle).toEqual({ concepto: 'Arrendamiento' });
  expect(datos.depositos).toEqual([]);
  expect(datos.estado.texto).toBe('Sin estado');
});

describe('soloFecha', () => {
  it('recorta la hora del registro', () => {
    expect(soloFecha('06/07/2026 09:46:41')).toBe('06/07/2026');
    expect(soloFecha(undefined)).toBe('');
  });
});

describe('presentarEstadoNpd', () => {
  it('conserva un estado desconocido en vez de inventarse uno', () => {
    expect(presentarEstadoNpd('En proceso')).toEqual({ tono: 'neutro', texto: 'En proceso' });
    expect(presentarEstadoNpd('Vigente').tono).toBe('exito');
  });
});
