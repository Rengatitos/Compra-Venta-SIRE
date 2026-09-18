/**
 * Un NPD llega con dos piezas de origen distinto pegadas (`app/services/sunat/
 * detracciones.py`): `cabecera` es la fila JSON del listado del periodo, con
 * las claves camelCase tal cual las emite SUNAT, y `detalle` es lo que el
 * scraping lee de la página del NPD, ya rotulado en castellano por el propio
 * portal y con la tabla de depósitos. Aquí se interpretan una sola vez para que
 * la ficha reciba texto listo para pintar sin perder nada de lo que vino.
 */

import type { NpdPeriodo } from '@/api/detracciones';
import type { TonoInsignia } from '@/components/ui/Badge';

import { formatearMoneda } from '@/lib/format';

import { aNumero } from './detalleSunat';

export interface PresentacionEstadoNpd {
  tono: TonoInsignia;
  texto: string;
}

/** Estados que devuelve la Consulta de NPD del portal SOL. */
const ESTADOS: Record<string, PresentacionEstadoNpd> = {
  vigente: { tono: 'exito', texto: 'Vigente' },
  'no vigente': { tono: 'neutro', texto: 'No vigente' },
  anulado: { tono: 'error', texto: 'Anulado' },
  utilizado: { tono: 'info', texto: 'Utilizado' },
};

export function presentarEstadoNpd(estado: unknown): PresentacionEstadoNpd {
  const texto = textoDe(estado);
  if (!texto) return { tono: 'neutro', texto: 'Sin estado' };
  return ESTADOS[texto.toLowerCase()] ?? { tono: 'neutro', texto };
}

/** Rótulos de las claves del listado. Las del detalle ya vienen en castellano. */
const ETIQUETAS_LISTADO: Record<string, string> = {
  numNpd: 'NPD',
  numRuc: 'RUC',
  razonSocial: 'Razón social',
  desRazonSocial: 'Razón social',
  fecRegistro: 'Registro',
  fecCreacion: 'Creación',
  fecLimitePago: 'Vencimiento',
  indicadorEstado: 'Indicador de estado',
  estado: 'Estado',
  importe: 'Importe',
};

/** Claves del listado que ya salen en el resumen de la ficha. */
const EN_RESUMEN = new Set([
  'numNpd',
  'numRuc',
  'razonSocial',
  'desRazonSocial',
  'fecRegistro',
  'fecCreacion',
  'fecLimitePago',
  'estado',
  'importe',
]);

/**
 * SUNAT rellena algunos campos del listado con el nombre de la propia columna
 * («razon social») en vez de dejarlos vacíos. Mostrarlos sería peor que nada.
 */
const RELLENOS = new Set(['', '-', '--', 'razon social', 'razón social']);

export function esRelleno(valor: string): boolean {
  return RELLENOS.has(valor.trim().toLowerCase());
}

/** Todo lo que el portal manda es texto o número suelto; el resto no se pinta. */
export function textoDe(valor: unknown): string {
  if (typeof valor === 'string') return valor.replace(/\s+/g, ' ').trim();
  if (typeof valor === 'number') return Number.isFinite(valor) ? String(valor) : '';
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No';
  return '';
}

/** `06/07/2026 09:46:41` → `06/07/2026`: en la tabla la hora no cabe ni aporta. */
export function soloFecha(valor: unknown): string {
  return textoDe(valor).split(' ')[0] ?? '';
}

/** `fecLimitePago` → `fec Limite Pago`, para una clave sin rótulo conocido. */
export function humanizarClave(clave: string): string {
  return clave.replaceAll('_', ' ').replace(/([a-z])([A-Z])/g, '$1 $2');
}

/**
 * Los rótulos de los depósitos son texto pintado por el portal («N° de cuenta
 * de detracciones»), con tildes, símbolos y mayúsculas que cambian de una
 * página a otra. Se comparan por su forma plana.
 */
function aplanar(clave: string): string {
  return clave
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .replace(/[^a-z0-9]+/gi, ' ')
    .trim()
    .toLowerCase();
}

/** Rótulos cortos: los del portal ocupan media pantalla cada uno. */
const ETIQUETAS_DEPOSITO: Record<string, string> = {
  'tipo de cuenta de detracciones': 'Tipo de cuenta',
  'n de cuenta de detracciones': 'Cuenta',
  'ruc del proveedor': 'RUC proveedor',
  'nombre o razon social del proveedor': 'Proveedor',
  'n de documento del adquiriente': 'Documento adquiriente',
  'nombre o razon social del adquiriente': 'Adquiriente',
  'tipo de operacion': 'Tipo de operación',
  'tipo de bien o servicio': 'Bien o servicio',
  'periodo tributario': 'Periodo',
  'tipo de comprobante': 'Comprobante',
  'serie y numero de comprobante': 'Serie y número',
  'monto de deposito s': 'Depósito S/',
};

export interface DatoNpd {
  clave: string;
  etiqueta: string;
  valor: string;
}

/**
 * Cada depósito trae una docena de campos. En una tabla eso son doce columnas
 * que no caben en el diálogo y obligan a arrastrar de izquierda a derecha para
 * leer una sola fila, así que cada depósito se pinta como una ficha: el
 * comprobante y el monto al frente y el resto en pares término/valor.
 */
export interface DepositoNpd {
  /** Posición en la tabla del portal: la única clave estable de una fila. */
  indice: number;
  /** Serie y número del comprobante, o «Depósito n» si el portal no lo manda. */
  titulo: string;
  monto: string;
  campos: readonly DatoNpd[];
}

export interface NpdNormalizado {
  numero: string;
  estado: PresentacionEstadoNpd;
  importe: number | null;
  /** RUC y razón social de quien generó el NPD, si los hay. */
  generadoPor: string;
  registro: string;
  creacion: string;
  vencimiento: string;
  datosPortal: readonly DatoNpd[];
  depositos: readonly DepositoNpd[];
  /** Claves del listado que no entran en el resumen. */
  otrosListado: readonly DatoNpd[];
  /** Lo que venga en `detalle` fuera de `cabecera` y `depositos`. */
  restoDetalle: Record<string, unknown>;
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

export function normalizarNpd(npd: NpdPeriodo): NpdNormalizado {
  const cabecera: Record<string, unknown> = npd.cabecera ?? {};
  const detalle = esObjeto(npd.detalle) ? npd.detalle : {};

  const numero = textoDe(npd.numero) || textoDe(cabecera.numNpd);
  const ruc = textoDe(cabecera.numRuc);
  const nombre =
    [cabecera.desRazonSocial, cabecera.razonSocial]
      .map(textoDe)
      .find((texto) => texto !== '' && !esRelleno(texto)) ?? '';

  const importe = aNumero(cabecera.importe);
  const registro = textoDe(cabecera.fecRegistro);
  const creacion = textoDe(cabecera.fecCreacion);
  const vencimiento = textoDe(cabecera.fecLimitePago);
  const estado = presentarEstadoNpd(cabecera.estado);

  // La página del NPD vuelve a dar casi todo lo que ya trae el listado, con
  // otro rótulo: el número, el RUC, el nombre, el monto, el estado y las
  // fechas. Repetirlo debajo del resumen es justo el ruido que se quiere
  // quitar, así que solo queda lo que el resumen no dice.
  const enResumen = [
    numero,
    ruc,
    nombre,
    estado.texto,
    registro,
    creacion,
    vencimiento,
    importe === null ? '' : formatearMoneda(importe, 'PEN'),
  ].filter((texto) => texto !== '');
  const yaVisto = (valor: string) =>
    enResumen.some(
      (visto) =>
        visto.toLowerCase() === valor.toLowerCase() ||
        // «06/07/2026 09:46» contra «06/07/2026 09:46:41»: el portal recorta los
        // segundos en su propia página. Sigue siendo el mismo dato.
        (valor.length >= 6 && visto.toLowerCase().startsWith(valor.toLowerCase())),
    );

  const camposPortal = esObjeto(detalle.cabecera) ? detalle.cabecera : null;
  const datosPortal = Object.entries(camposPortal ?? {})
    .map(([etiqueta, valor]) => ({ clave: etiqueta, etiqueta, valor: textoDe(valor) }))
    .filter((dato) => dato.valor !== '' && !yaVisto(dato.valor));

  const filasDeposito = Array.isArray(detalle.depositos)
    ? detalle.depositos.filter(esObjeto)
    : null;

  const depositos = (filasDeposito ?? []).map((fila, indice) => {
    const campos: DatoNpd[] = [];
    let titulo = '';
    let monto = '';
    for (const [clave, crudo] of Object.entries(fila)) {
      const plana = aplanar(clave);
      const valor = textoDe(crudo);
      if (valor === '') continue;
      if (!titulo && /serie/.test(plana)) {
        titulo = valor;
        continue;
      }
      if (!monto && /monto|importe|deposito/.test(plana)) {
        const numero = aNumero(valor);
        monto = numero === null ? valor : formatearMoneda(numero, 'PEN');
        continue;
      }
      // El adquiriente de un depósito es siempre quien generó el NPD, que ya
      // encabeza la ficha; lo mismo con cualquier otro campo ya visto.
      if (yaVisto(valor)) continue;
      campos.push({ clave, etiqueta: ETIQUETAS_DEPOSITO[plana] ?? clave, valor });
    }
    return { indice, titulo: titulo || `Depósito ${indice + 1}`, monto, campos };
  });

  const otrosListado = Object.entries(cabecera)
    .filter(([clave]) => !EN_RESUMEN.has(clave))
    .map(([clave, valor]) => ({
      clave,
      etiqueta: ETIQUETAS_LISTADO[clave] ?? humanizarClave(clave),
      valor: textoDe(valor),
    }))
    .filter((dato) => !esRelleno(dato.valor));

  const restoDetalle = Object.fromEntries(
    Object.entries(detalle).filter(
      ([clave]) =>
        !(clave === 'cabecera' && camposPortal) && !(clave === 'depositos' && filasDeposito),
    ),
  );

  return {
    numero,
    estado,
    importe,
    generadoPor: [ruc, nombre].filter(Boolean).join(' · '),
    registro,
    creacion,
    vencimiento,
    datosPortal,
    depositos,
    otrosListado,
    restoDetalle,
  };
}
