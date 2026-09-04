import { describe, expect, it } from 'vitest';

import type { ComprobanteResponse, FilaReporte } from '@/types/api';

import {
  comparable,
  descuadra,
  presentarFuente,
  tieneDetalle,
  tieneGlosa,
  tienePdf,
} from '../coberturaAuditoria';

function comprobante(parcial: Partial<ComprobanteResponse> = {}): ComprobanteResponse {
  return {
    serie_numero: 'F001-1',
    libro: 'compras',
    origen: 'sire',
    tipo_cp: '01',
    tipo_cp_descripcion: 'FACTURA',
    serie: 'F001',
    numero: '1',
    tipo_doc_identidad: '6',
    documento_contraparte: '20129646099',
    razon_social: 'ELECTROCENTRO S.A.',
    fecha_emision: '2026-06-15',
    fecha_vencimiento: null,
    moneda: 'PEN',
    tipo_cambio: 0,
    porcentaje_igv: 18,
    base_imponible: 100,
    igv: 18,
    base_imponible_dg: 100,
    igv_dg: 18,
    base_imponible_dgng: 0,
    igv_dgng: 0,
    base_imponible_dng: 0,
    igv_dng: 0,
    exonerado: 0,
    inafecto: 0,
    no_gravado: 0,
    isc: 0,
    icbper: 0,
    otros_tributos: 0,
    total: 118,
    estado_procesamiento: 'sire_recibido',
    analisis: null,
    detalle_sunat: [],
    pdf_sunat: null,
    documentos_modificados: [],
    ...parcial,
  };
}

function fila(parcial: Partial<FilaReporte> = {}): FilaReporte {
  return {
    serie_numero: 'F001-1',
    tipo_cp: '01',
    tipo_cp_descripcion: 'FACTURA',
    fecha_emision: '2026-06-15',
    documento_contraparte: '20129646099',
    razon_social: 'ELECTROCENTRO S.A.',
    moneda: 'PEN',
    base_imponible: 100,
    igv: 18,
    total: 118,
    importe_detalle: null,
    diferencia: null,
    lineas_detalle: 0,
    detalle_sunat: [],
    glosa: '',
    cuenta_base: '',
    cuenta_total: '',
    observaciones: '',
    fuentes: [],
    pdf: null,
    ...parcial,
  };
}

describe('cobertura por comprobante', () => {
  it('el detalle depende de que el scraper haya traído líneas', () => {
    expect(tieneDetalle(comprobante()).texto).toBe('No');
    expect(tieneDetalle(comprobante({ detalle_sunat: [{}] })).texto).toBe('Sí');
  });

  it('el PDF depende del puntero que escribe el trabajo de descarga', () => {
    expect(tienePdf(comprobante()).texto).toBe('No');
    expect(
      tienePdf(
        comprobante({ pdf_sunat: { ruta: 'x/compras/2026/06/facturas/F001-1.pdf', bytes: 4, descargado_en: null } }),
      ).texto,
    ).toBe('Sí');
  });

  it('la glosa sale del RAG o, si no la hay, de la descripción del análisis', () => {
    expect(tieneGlosa(comprobante()).texto).toBe('No');

    const conRag = comprobante({
      analisis: {
        detalle: [],
        cuenta_contable: null,
        centro_costos: null,
        condicion_igv: null,
        resultado: null,
        confianza: null,
        estado: null,
        documentos: null,
        descripcion: null,
        observaciones: null,
        rag: {
          codigo_comprobante: null,
          codigo_identidad: null,
          cuenta_base: null,
          cuenta_total: null,
          glosa: 'POR LA COMPRA DE COMBUSTIBLE',
          respuesta_cuentas: null,
        },
      },
    });
    expect(tieneGlosa(conRag).texto).toBe('Sí');
  });
});

describe('descuadre', () => {
  it('una diferencia por encima del céntimo descuadra', () => {
    expect(descuadra(fila({ diferencia: 0.5 }))).toBe(true);
    expect(descuadra(fila({ diferencia: -0.5 }))).toBe(true);
  });

  it('la tolerancia de un céntimo absorbe el redondeo', () => {
    // Contasis divide el total entre 1.18 sin redondear y SUNAT reporta dos
    // decimales: sin tolerancia nada cuadraría nunca.
    expect(descuadra(fila({ diferencia: 0.01 }))).toBe(false);
    expect(descuadra(fila({ diferencia: 0 }))).toBe(false);
  });

  it('sin detalle extraído no cuadra ni descuadra: falta el dato', () => {
    // Es la distinción que evita que un periodo sin recolectar se lea como un
    // periodo conciliado.
    const sinComparar = fila({ diferencia: null });
    expect(descuadra(sinComparar)).toBe(false);
    expect(comparable(sinComparar)).toBe(false);
  });

  it('con detalle extraído la fila es comparable aunque cuadre', () => {
    expect(comparable(fila({ diferencia: 0 }))).toBe(true);
  });
});

describe('fuentes', () => {
  it('cada fuente tiene un rótulo legible', () => {
    expect(presentarFuente('propuesta_sire').texto).toBe('Propuesta SIRE');
    expect(presentarFuente('detalle_portal_sol').texto).toBe('Portal SOL');
    expect(presentarFuente('pdf_descargado').texto).toBe('PDF');
  });

  it('una fuente que el backend añada después no llega cruda a la pantalla vacía', () => {
    // No se inventa un rótulo, pero tampoco se pierde el dato.
    const desconocida = presentarFuente('algo_nuevo' as never);
    expect(desconocida.texto).toBe('algo_nuevo');
    expect(desconocida.tono).toBe('neutro');
  });
});
