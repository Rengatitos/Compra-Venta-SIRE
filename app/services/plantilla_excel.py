"""Exportación al formato oficial «REGISTRO DE COMPRAS Y VENTAS» de Contasis.

La plantilla vive en `app/resources/plantilla_registro.xlsx` (copia de
`source/PLANTILLA REGISTRO DE COMPRAS Y VENTAS.xlsx`, que está fuera del control
de versiones y no entra a la imagen de Docker). No se reconstruye el layout a
mano: se abre el archivo real y se escriben las filas debajo de sus encabezados,
así el formato queda idéntico al que espera el contador.

Del análisis IA viajan la cuenta contable y la glosa. El centro de costos no:
la plantilla pide el *código* del catálogo de Contasis (9 caracteres) y la IA
devuelve un nombre descriptivo, así que escribirlo recortado inventaría códigos
que colisionan entre sí.
"""

from __future__ import annotations

import io
from copy import copy
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.comprobante import Libro, normalizar_fecha

RUTA_PLANTILLA = Path(__file__).resolve().parents[1] / "resources" / "plantilla_registro.xlsx"

# Las filas 1-13 son las notas de uso, el título y los tres niveles de
# encabezado de la plantilla. Los datos empiezan en la 14.
PRIMERA_FILA_DATOS = 14

# El nombre de la hoja de compras trae espacios de más: es literal dentro del
# archivo y openpyxl la busca tal cual.
HOJAS: dict[Libro, str] = {
    Libro.COMPRAS: "FORMATO_ COMPRAS ",
    Libro.VENTAS: "FORMATO_VENTAS",
}

# La fila 13 de la plantilla documenta `dd/mm/yyyy`, pero las celdas heredan
# `mm-dd-yy`. Se fuerza el formato documentado.
FORMATO_FECHA = "DD/MM/YYYY"

# Contasis identifica la moneda con un solo carácter.
MONEDAS: dict[str, str] = {"PEN": "S", "USD": "D"}

# Tasa general. Sólo se usa como respaldo cuando el comprobante tiene IGV pero
# SUNAT no mandó la tasa: si no hay IGV, la celda se queda vacía en vez de
# afirmar un 18 % que no corresponde.
TASA_IGV = 18

# Anchos que declara la fila 13 de la plantilla para las columnas de texto que
# llena la IA. Pasarse no es inofensivo: Contasis trunca por su cuenta al
# importar y el corte cae donde caiga.
MAX_CUENTA_CONTABLE = 10
MAX_GLOSA = 60

_plantilla: bytes | None = None


def _bytes_plantilla() -> bytes:
    global _plantilla
    if _plantilla is None:
        _plantilla = RUTA_PLANTILLA.read_bytes()
    return _plantilla


def _texto(valor: Any) -> str | None:
    texto = "" if valor is None else str(valor).strip()
    return texto or None


def _entero_o_texto(valor: Any) -> int | str | None:
    """Serie y tipo van como texto; correlativos y documentos, como número.

    Es lo que hace el archivo de ejemplo de la plantilla: `E001` en la serie,
    pero `158` y `20612495522` como enteros.
    """
    texto = _texto(valor)
    if texto is None:
        return None
    return int(texto) if texto.isdigit() else texto


# El tipo de cambio no es un importe: la plantilla lo declara «(10,4)
# NUMERICO» y redondearlo a dos decimales convertía un 3.387 en 3.39.
DECIMALES_IMPORTE = 2
DECIMALES_TIPO_CAMBIO = 4


def _monto(valor: Any, decimales: int = DECIMALES_IMPORTE) -> float | None:
    """Un cero se escribe como celda vacía, no como `0`.

    Se redondea porque el formato de la plantilla sólo redondea lo que se
    *ve*: un `126779.6610169492` se guardaba entero en la celda y reaparecía
    en cuanto alguien miraba la barra de fórmulas o reexportaba el archivo.
    """
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return round(numero, decimales) or None


def _suma(*valores: Any) -> float:
    total = 0.0
    for valor in valores:
        try:
            total += float(valor)
        except (TypeError, ValueError):
            continue
    return total


def _moneda(valor: Any) -> str:
    return MONEDAS.get(_texto(valor) or "PEN", "S")


def _recortar(valor: Any, tope: int) -> str | None:
    """Texto recortado a `tope`, cortando en el último espacio que quepa."""
    texto = _texto(valor)
    if texto is None or len(texto) <= tope:
        return texto
    corte = texto[:tope]
    espacio = corte.rfind(" ")
    # Sólo se corta por palabra si eso no deja un resto ridículo: con una
    # primera palabra larguísima es mejor el corte seco.
    if espacio > tope // 2:
        corte = corte[:espacio]
    return corte.rstrip(" ,;.-") or None


def _analisis(comprobante: dict[str, Any]) -> dict[str, Any]:
    analisis = comprobante.get("analisis")
    return analisis if isinstance(analisis, dict) else {}


def _glosa(comprobante: dict[str, Any]) -> str | None:
    """Descripción corta de la operación para la columna de glosa.

    Con un único ítem su nombre es la mejor glosa posible y casi siempre cabe
    entera; con varios, describir sólo el primero engañaría, así que se usa el
    resumen que hace la IA del comprobante completo.
    """
    analisis = _analisis(comprobante)
    detalle = analisis.get("detalle")
    if isinstance(detalle, list) and len(detalle) == 1 and isinstance(detalle[0], dict):
        glosa = _recortar(detalle[0].get("producto"), MAX_GLOSA)
        if glosa:
            return glosa
    return _recortar(analisis.get("descripcion"), MAX_GLOSA)


def _cuenta_contable(comprobante: dict[str, Any]) -> str | None:
    return _recortar(_analisis(comprobante).get("cuenta_contable"), MAX_CUENTA_CONTABLE)


def _tasa_igv(comprobante: dict[str, Any]) -> float | int | None:
    """Tasa declarada por SUNAT; la general sólo si hay IGV y no vino tasa."""
    tasa = _monto(comprobante.get("porcentaje_igv"))
    if tasa is not None:
        return tasa
    return TASA_IGV if _monto(comprobante.get("igv")) else None


def _fechas(comprobante: dict[str, Any]) -> tuple[date | None, date | None]:
    emision = normalizar_fecha(comprobante.get("fecha_emision"))
    vencimiento = normalizar_fecha(comprobante.get("fecha_vencimiento")) or emision
    return emision, vencimiento


def _rag(comprobante: dict[str, Any]) -> dict[str, Any]:
    return ((comprobante.get("analisis") or {}).get("rag") or {})


def _fila_compras(comprobante: dict[str, Any]) -> dict[str, Any]:
    emision, vencimiento = _fechas(comprobante)
    rag = _rag(comprobante)
    return {
        "A": emision,
        "B": vencimiento,
        "C": _texto(rag.get("codigo_comprobante") or comprobante.get("tipo_cp")),
        "D": _texto(comprobante.get("serie")),
        "F": _entero_o_texto(comprobante.get("numero")),
        "G": _entero_o_texto(
            rag.get("codigo_identidad") or comprobante.get("tipo_doc_identidad")
        ),
        "H": _entero_o_texto(comprobante.get("documento_contraparte")),
        "I": _texto(comprobante.get("razon_social")),
        # Los tres destinos van en columnas distintas. Se usa el desglose y no
        # `base_imponible`/`igv`, que son la suma de los tres: mandarlo todo a
        # J/K declaraba como gravado lo destinado a operaciones no gravadas.
        "J": _monto(comprobante.get("base_imponible_dg")),
        "K": _monto(comprobante.get("igv_dg")),
        "L": _monto(comprobante.get("base_imponible_dgng")),
        "M": _monto(comprobante.get("igv_dgng")),
        "N": _monto(comprobante.get("base_imponible_dng")),
        "O": _monto(comprobante.get("igv_dng")),
        # Adquisiciones no gravadas. El SIRE las manda agrupadas en
        # `no_gravado`; sin sumarlo esta columna salía en cero para todas
        # las compras exoneradas o inafectas.
        "P": _monto(
            _suma(
                comprobante.get("exonerado"),
                comprobante.get("inafecto"),
                comprobante.get("no_gravado"),
            )
        ),
        "Q": _monto(comprobante.get("isc")),
        "R": _monto(comprobante.get("otros_tributos")),
        "S": _monto(comprobante.get("total")),
        "W": _monto(comprobante.get("tipo_cambio"), DECIMALES_TIPO_CAMBIO),
        "AB": _moneda(comprobante.get("moneda")),
        "AD": vencimiento,
        "AF": _cuenta_contable(comprobante),
        "AR": _tasa_igv(comprobante),
        "AS": _glosa(comprobante),
    }


def _fila_ventas(comprobante: dict[str, Any]) -> dict[str, Any]:
    emision, vencimiento = _fechas(comprobante)
    rag = _rag(comprobante)
    return {
        "A": emision,
        "B": vencimiento,
        "C": _texto(rag.get("codigo_comprobante") or comprobante.get("tipo_cp")),
        "D": _texto(comprobante.get("serie")),
        "E": _entero_o_texto(comprobante.get("numero")),
        "F": _entero_o_texto(
            rag.get("codigo_identidad") or comprobante.get("tipo_doc_identidad")
        ),
        "G": _entero_o_texto(comprobante.get("documento_contraparte")),
        "H": _texto(comprobante.get("razon_social")),
        "J": _monto(comprobante.get("base_imponible")),
        "K": _monto(comprobante.get("exonerado")),
        "L": _monto(comprobante.get("inafecto")),
        "M": _monto(comprobante.get("isc")),
        "N": _monto(comprobante.get("igv")),
        "O": _monto(comprobante.get("otros_tributos")),
        "P": _monto(comprobante.get("total")),
        "Q": _monto(comprobante.get("tipo_cambio"), DECIMALES_TIPO_CAMBIO),
        "V": _moneda(comprobante.get("moneda")),
        "X": vencimiento,
        # En la hoja de ventas la moneda es la V: AB es la cuenta contable.
        "AB": _cuenta_contable(comprobante),
        "AL": _tasa_igv(comprobante),
        "AM": _glosa(comprobante),
    }


# Columnas de fecha y celda que rotula el pie de totales.
_COLUMNAS_FECHA = {Libro.COMPRAS: ("A", "B", "AD"), Libro.VENTAS: ("A", "B", "X")}
_ROTULO_TOTAL = {Libro.COMPRAS: "A", Libro.VENTAS: "G"}

# Columna «MONEDA» del formato Contasis, que lleva un solo carácter (S o D).
_COLUMNA_MONEDA = {Libro.COMPRAS: "AB", Libro.VENTAS: "V"}

# Las columnas de dinero: son las que llevan símbolo de moneda y las que suma
# el pie. Coinciden porque todo lo que es un importe se totaliza. El tipo de
# cambio y el porcentaje de IGV quedan fuera a propósito: no son dinero.
_COLUMNAS_IMPORTE = {
    Libro.COMPRAS: ("J", "K", "L", "M", "N", "O", "P", "Q", "R", "S"),
    Libro.VENTAS: ("J", "K", "L", "M", "N", "O", "P"),
}
_COLUMNAS_TOTAL = _COLUMNAS_IMPORTE

# El formato contable de la plantilla, con el símbolo delante. Sin él las
# columnas de importe son números pelados —«149600» podía ser un monto, una
# cantidad o un correlativo—, y en un registro con soles y dólares mezclados
# tampoco había forma de saber cuál se estaba mirando: la moneda vivía sólo en
# la columna V/AB, a treinta columnas de distancia y como una letra suelta.
_FORMATO_IMPORTE = {
    "PEN": r'_ * "S/"\ #,##0.00_ ;_ * "S/"\ \-#,##0.00_ ;_ * "-"??_ ;_ @_ ',
    "USD": r'_ * "US$"\ #,##0.00_ ;_ * "US$"\ \-#,##0.00_ ;_ * "-"??_ ;_ @_ ',
}
# Una moneda que no reconocemos se queda con el formato contable sin símbolo:
# es mejor un número bien alineado que un símbolo inventado.
_FORMATO_IMPORTE_NEUTRO = r'_ * #,##0.00_ ;_ * \-#,##0.00_ ;_ * "-"??_ ;_ @_ '

_MAPEOS = {Libro.COMPRAS: _fila_compras, Libro.VENTAS: _fila_ventas}


def _formato_importe(moneda: Any) -> str:
    return _FORMATO_IMPORTE.get(_texto(moneda) or "PEN", _FORMATO_IMPORTE_NEUTRO)


def _prototipos(hoja: Worksheet) -> dict[str, Any]:
    """Estilo de cada columna en la primera fila de datos de la plantilla."""
    return {celda.column_letter: celda._style for celda in hoja[PRIMERA_FILA_DATOS]}


def _limpiar_ejemplos(hoja: Worksheet) -> None:
    """Borra las filas de ejemplo y el pie de totales que trae la plantilla.

    Vienen con fórmulas (`=+A14`, `=+S14/1.18`) que se recalcularían sobre datos
    reales. Los rangos combinados de los encabezados están en las filas 8-12, así
    que solo hay que desarmar los del pie antes de borrar.
    """
    for rango in list(hoja.merged_cells.ranges):
        if rango.min_row >= PRIMERA_FILA_DATOS:
            hoja.unmerge_cells(str(rango))

    if hoja.max_row >= PRIMERA_FILA_DATOS:
        hoja.delete_rows(PRIMERA_FILA_DATOS, hoja.max_row - PRIMERA_FILA_DATOS + 1)


def _escribir_fila(
    hoja: Worksheet,
    indice: int,
    valores: dict[str, Any],
    prototipos: dict[str, Any],
    columnas_fecha: tuple[str, ...],
    columnas_importe: tuple[str, ...],
    moneda: Any,
) -> None:
    for letra, estilo in prototipos.items():
        hoja[f"{letra}{indice}"]._style = copy(estilo)

    formato_importe = _formato_importe(moneda)
    for letra, valor in valores.items():
        if valor is None:
            continue
        celda = hoja[f"{letra}{indice}"]
        celda.value = valor
        if letra in columnas_fecha:
            celda.number_format = FORMATO_FECHA
        elif letra in columnas_importe:
            # El símbolo va por fila, no por columna: en un mismo registro
            # conviven comprobantes en soles y en dólares.
            celda.number_format = formato_importe


# Rótulo y carácter de la columna MONEDA, por moneda.
_TOTALES_POR_MONEDA = (("PEN", "TOTAL S/", "S"), ("USD", "TOTAL US$", "D"))


def _escribir_totales(
    hoja: Worksheet, indice: int, ultima: int, libro: Libro, monedas: set[str]
) -> int:
    """Un pie de totales por cada moneda presente. Devuelve la fila siguiente.

    Sumar en una sola fila un registro con soles y dólares daba un número que
    no significa nada. Con `SUMIF` sobre la columna MONEDA cada total agrega
    sólo lo suyo, y el rótulo dice de qué moneda habla.
    """
    columna_moneda = _COLUMNA_MONEDA[libro]
    rango_moneda = (
        f"${columna_moneda}${PRIMERA_FILA_DATOS}:${columna_moneda}${ultima}"
    )
    # Si sólo hay una moneda no hace falta condicionar nada, y el pie queda
    # como el que espera la plantilla.
    unica = len(monedas) <= 1

    for codigo, rotulo, marca in _TOTALES_POR_MONEDA:
        if codigo not in monedas:
            continue
        hoja[f"{_ROTULO_TOTAL[libro]}{indice}"] = rotulo
        for letra in _COLUMNAS_TOTAL[libro]:
            rango = f"{letra}{PRIMERA_FILA_DATOS}:{letra}{ultima}"
            celda = hoja[f"{letra}{indice}"]
            celda.value = (
                f"=SUM({rango})"
                if unica
                else f'=SUMIF({rango_moneda},"{marca}",{rango})'
            )
            celda.number_format = _FORMATO_IMPORTE.get(codigo, _FORMATO_IMPORTE_NEUTRO)
        indice += 1

    # Monedas que no son ni soles ni dólares: no se inventa un pie para ellas,
    # pero tampoco pueden desaparecer del archivo sin decirlo.
    otras = monedas - {codigo for codigo, _, _ in _TOTALES_POR_MONEDA}
    if otras:
        hoja[f"{_ROTULO_TOTAL[libro]}{indice}"] = (
            "Sin totalizar: " + ", ".join(sorted(otras))
        )
        indice += 1

    return indice


def excel_plantilla(comprobantes: list[dict[str, Any]], libro: Libro) -> io.BytesIO:
    """Genera el registro del libro pedido sobre la plantilla oficial."""
    wb = load_workbook(io.BytesIO(_bytes_plantilla()))

    for nombre in wb.sheetnames:
        if nombre != HOJAS[libro]:
            wb.remove(wb[nombre])

    hoja = wb[HOJAS[libro]]
    prototipos = _prototipos(hoja)
    _limpiar_ejemplos(hoja)

    mapear = _MAPEOS[libro]
    columnas_fecha = _COLUMNAS_FECHA[libro]
    columnas_importe = _COLUMNAS_IMPORTE[libro]

    indice = PRIMERA_FILA_DATOS
    monedas: set[str] = set()
    for comprobante in comprobantes:
        moneda = _texto(comprobante.get("moneda")) or "PEN"
        monedas.add(moneda)
        _escribir_fila(
            hoja,
            indice,
            mapear(comprobante),
            prototipos,
            columnas_fecha,
            columnas_importe,
            moneda,
        )
        indice += 1

    if comprobantes:
        _escribir_totales(hoja, indice, indice - 1, libro, monedas)

    salida = io.BytesIO()
    wb.save(salida)
    salida.seek(0)
    return salida
