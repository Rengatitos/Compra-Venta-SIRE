/**
 * El detalle del portal SOL llega como `list[Any]`: lo arma el scraping leyendo
 * las celdas del popup (`app/services/scraping_sunat.py`), así que todo son
 * cadenas y el formato depende de cómo pinte SUNAT esa tabla. Aquí se
 * interpreta una sola vez para que la pantalla reciba números y texto limpio.
 */

/**
 * La celda de descripción del popup trae, además del nombre del producto, una
 * copia de las columnas numéricas pegada con este separador:
 * `COCA COLA VR 1.5L X08 RF@#@   -4  @#@33.34@#@.00@#@.00@#@.00@#@16.67`.
 * Solo interesa lo que va antes del primer separador.
 */
const SEPARADOR_SUNAT = '@#@';

export interface ItemDetalle {
  /** Posición original: es la única clave estable de una fila del popup. */
  indice: number;
  codigo: string;
  descripcion: string;
  unidadMedida: string;
  cantidad: number | null;
  valorUnitario: number | null;
  precioUnitario: number | null;
  valorVenta: number | null;
  icbper: number | null;
}

export interface DetalleNormalizado {
  items: readonly ItemDetalle[];
  /** Filas que no tenían la forma esperada. Se cuentan para no fingir que no existen. */
  descartadas: number;
  totalValorVenta: number;
  totalIcbper: number;
}

function limpiarTexto(valor: unknown): string {
  if (typeof valor !== 'string') return '';
  return valor.replace(/\s+/g, ' ').trim();
}

export function limpiarDescripcion(valor: unknown): string {
  if (typeof valor !== 'string') return '';
  const [nombre] = valor.split(SEPARADOR_SUNAT);
  return limpiarTexto(nombre ?? '');
}

/**
 * `"0.50"`, `".00"` y `"1,234.56"` son todos válidos en el popup. Devuelve
 * `null` en lugar de `0` cuando no hay número: un importe ausente y uno en cero
 * no significan lo mismo en un comprobante.
 */
export function aNumero(valor: unknown): number | null {
  if (typeof valor === 'number') return Number.isFinite(valor) ? valor : null;
  if (typeof valor !== 'string') return null;

  const limpio = valor.replace(/\s/g, '').replace(/,/g, '');
  if (limpio === '') return null;

  const numero = Number(limpio);
  return Number.isFinite(numero) ? numero : null;
}

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
}

export function normalizarDetalleSunat(filas: readonly unknown[]): DetalleNormalizado {
  const items: ItemDetalle[] = [];
  let descartadas = 0;

  filas.forEach((fila, indice) => {
    if (!esObjeto(fila)) {
      descartadas += 1;
      return;
    }

    const descripcion = limpiarDescripcion(fila.descripcion);
    const codigo = limpiarTexto(fila.codigo);

    // Una fila sin nombre ni código no describe nada: es ruido de la tabla.
    if (!descripcion && !codigo) {
      descartadas += 1;
      return;
    }

    items.push({
      indice,
      codigo,
      descripcion,
      unidadMedida: limpiarTexto(fila.unidad_medida),
      cantidad: aNumero(fila.cantidad),
      valorUnitario: aNumero(fila.valor_unitario),
      precioUnitario: aNumero(fila.precio_unitario),
      valorVenta: aNumero(fila.valor_venta),
      icbper: aNumero(fila.icbper),
    });
  });

  const sumar = (leer: (item: ItemDetalle) => number | null) =>
    items.reduce((acumulado, item) => acumulado + (leer(item) ?? 0), 0);

  return {
    items,
    descartadas,
    totalValorVenta: sumar((item) => item.valorVenta),
    totalIcbper: sumar((item) => item.icbper),
  };
}
