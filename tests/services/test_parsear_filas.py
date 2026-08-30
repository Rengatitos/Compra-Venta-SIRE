"""`_parsear_filas` es la única parte del scraping con reglas de negocio.

Se separó del navegador precisamente para poder fijarlas aquí: la tabla del
popup mezcla las líneas de ítem con la cabecera del comprobante y los totales,
y todas comparten estructura. Lo único que las distingue es que la primera
celda de un ítem es un número y que su descripción no es un rótulo.
"""

from __future__ import annotations

from app.services.scraping_sunat import _parsear_filas

# Una línea real: cantidad, unidad, código, descripción, y los importes.
FILA_ITEM = ["2.00", "NIU", "P001", "Cuaderno A4", "5.00", "5.90", "10.00", "0.00"]


def test_extrae_una_linea_de_item():
    items = _parsear_filas([FILA_ITEM])

    assert items == [
        {
            "cantidad": "2.00",
            "unidad_medida": "NIU",
            "codigo": "P001",
            "descripcion": "Cuaderno A4",
            "valor_unitario": "5.00",
            "precio_unitario": "5.90",
            "valor_venta": "10.00",
            "icbper": "0.00",
        }
    ]


def test_descarta_la_cabecera_de_la_tabla():
    cabecera = [
        "Cant.(A)", "U.M.", "Código", "Descripción",
        "Valor Unit.(B)", "Precio Unit.", "Valor V.(A)*(B)", "ICBPER",
    ]

    assert _parsear_filas([cabecera]) == []


def test_descarta_totales_aunque_empiecen_con_numero():
    # El pie de la tabla sí trae un número en la primera celda, así que el
    # filtro por descripción es el que lo tumba.
    total = ["0.00", "", "", "Total Venta", "0.00", "0.00", "1180.00", "0.00"]

    assert _parsear_filas([total]) == []


def test_ignora_filas_de_maquetacion():
    # Las filas de layout del popup traen una o dos celdas sueltas.
    assert _parsear_filas([[], ["   "], ["a", "b", "c", "d", "e"]]) == []


def test_recorta_los_espacios_del_html():
    fila = ["  2.00 ", "\nNIU\t", " P001", "  Cuaderno A4  ", "5.00", "5.90", "10.00", "0.00"]

    (item,) = _parsear_filas([fila])

    assert item["cantidad"] == "2.00"
    assert item["unidad_medida"] == "NIU"
    assert item["descripcion"] == "Cuaderno A4"


def test_rellena_las_columnas_que_falten():
    # SUNAT omite ICBPER y valor de venta en algunos comprobantes.
    (item,) = _parsear_filas([["1.00", "NIU", "P001", "Lapicero", "3.00", "3.54"]])

    assert item["valor_venta"] == ""
    assert item["icbper"] == ""


def test_acepta_cantidades_con_separador_de_miles():
    fila = ["1,500.00", "KGM", "P9", "Arroz", "2.00", "2.36", "3000.00", "0.00"]

    (item,) = _parsear_filas([fila])

    assert item["cantidad"] == "1,500.00"


def test_conserva_el_orden_y_solo_los_items():
    otro = ["1.00", "NIU", "P002", "Borrador", "1.00", "1.18", "1.00", "0.00"]
    filas = [
        ["Tipo de Comprobante", "Factura"],
        FILA_ITEM,
        ["0.00", "", "", "Sumatoria", "0.00", "0.00", "11.00", "0.00"],
        otro,
    ]

    items = _parsear_filas(filas)

    assert [i["descripcion"] for i in items] == ["Cuaderno A4", "Borrador"]
