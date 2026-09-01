"""Exportación al formato oficial «REGISTRO DE COMPRAS Y VENTAS» de Contasis.

La plantilla vive en `app/resources/plantilla_registro.xlsx` (copia de
`source/PLANTILLA REGISTRO DE COMPRAS Y VENTAS.xlsx`, que está fuera del control
de versiones y no entra a la imagen de Docker). No se reconstruye el layout a
mano: se abre el archivo real y se escriben las filas debajo de sus encabezados,
así el formato queda idéntico al que espera el contador.

Los importes y datos tributarios salen del SIRE. Los códigos contables y la
glosa se completan únicamente con la clasificación guardada por la API RAG.
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

TASA_IGV = 18

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


def _monto(valor: Any) -> float | None:
    """Un cero se escribe como celda vacía, no como `0`."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero or None


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
        "J": _monto(comprobante.get("base_imponible")),
        "K": _monto(comprobante.get("igv")),
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
        "W": _monto(comprobante.get("tipo_cambio")),
        "AB": _moneda(comprobante.get("moneda")),
        "AD": vencimiento,
        "AF": _texto(rag.get("cuenta_base")),
        "AH": _texto(rag.get("cuenta_total")),
        "AR": TASA_IGV,
        "AS": _texto(rag.get("glosa")),
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
        "Q": _monto(comprobante.get("tipo_cambio")),
        "V": _moneda(comprobante.get("moneda")),
        "X": vencimiento,
        "AB": _texto(rag.get("cuenta_base")),
        "AD": _texto(rag.get("cuenta_total")),
        "AL": TASA_IGV,
        "AM": _texto(rag.get("glosa")),
    }


# Columnas de fecha, celda que rotula el pie de totales y columnas que se suman.
_COLUMNAS_FECHA = {Libro.COMPRAS: ("A", "B", "AD"), Libro.VENTAS: ("A", "B", "X")}
_ROTULO_TOTAL = {Libro.COMPRAS: "A", Libro.VENTAS: "G"}
_COLUMNAS_TOTAL = {
    Libro.COMPRAS: ("J", "K", "L", "M", "N", "O", "P", "Q", "R", "S"),
    Libro.VENTAS: ("J", "K", "L", "M", "N", "O", "P"),
}
_MAPEOS = {Libro.COMPRAS: _fila_compras, Libro.VENTAS: _fila_ventas}


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
) -> None:
    for letra, estilo in prototipos.items():
        hoja[f"{letra}{indice}"]._style = copy(estilo)

    for letra, valor in valores.items():
        if valor is None:
            continue
        celda = hoja[f"{letra}{indice}"]
        celda.value = valor
        if letra in columnas_fecha:
            celda.number_format = FORMATO_FECHA


def _escribir_total(hoja: Worksheet, indice: int, ultima: int, libro: Libro) -> None:
    hoja[f"{_ROTULO_TOTAL[libro]}{indice}"] = "TOTAL"
    for letra in _COLUMNAS_TOTAL[libro]:
        celda = hoja[f"{letra}{indice}"]
        celda.value = f"=SUM({letra}{PRIMERA_FILA_DATOS}:{letra}{ultima})"
        celda.number_format = "#,##0.00"


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

    indice = PRIMERA_FILA_DATOS
    for comprobante in comprobantes:
        _escribir_fila(hoja, indice, mapear(comprobante), prototipos, columnas_fecha)
        indice += 1

    if comprobantes:
        _escribir_total(hoja, indice, indice - 1, libro)

    salida = io.BytesIO()
    wb.save(salida)
    salida.seek(0)
    return salida
