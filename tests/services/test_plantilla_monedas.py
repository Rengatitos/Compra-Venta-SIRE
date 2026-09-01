"""El registro mezcla soles y dólares, y tiene que verse cuál es cuál.

SUNAT devuelve cada comprobante en la moneda en que se emitió, así que un
periodo real trae las dos. Antes las columnas de importe eran números pelados
—«149600» lo mismo podía ser un monto que un correlativo— y la moneda vivía
sola, como una letra `S` o `D`, a treinta columnas de distancia. El pie, además,
sumaba soles con dólares en la misma celda.
"""

from __future__ import annotations

from openpyxl import load_workbook

from app.domain.comprobante import Libro
from app.services import plantilla_excel


def _comprobante(moneda: str, total: float, tipo_cambio: float = 1) -> dict:
    base = round(total / 1.18, 2)
    return {
        "tipo_cp": "01", "serie": "F001", "numero": "1",
        "tipo_doc_identidad": "6", "documento_contraparte": "20129646099",
        "razon_social": "ACME S.A.", "fecha_emision": "2026-08-03",
        "fecha_vencimiento": "2026-08-03", "moneda": moneda,
        "tipo_cambio": tipo_cambio, "porcentaje_igv": 18,
        "base_imponible": base, "igv": round(total - base, 2),
        "exonerado": 0, "inafecto": 0, "no_gravado": 0, "isc": 0, "icbper": 0,
        "otros_tributos": 0, "total": total, "analisis": None,
        "base_imponible_dg": base, "igv_dg": round(total - base, 2),
        "base_imponible_dgng": 0, "igv_dgng": 0,
        "base_imponible_dng": 0, "igv_dng": 0,
    }


def _hoja(comprobantes: list[dict], libro: Libro = Libro.COMPRAS):
    wb = load_workbook(plantilla_excel.excel_plantilla(comprobantes, libro))
    return wb[plantilla_excel.HOJAS[libro]]


class TestMonedaEnLosImportes:
    def test_una_fila_en_soles_lleva_el_simbolo_de_soles(self):
        hoja = _hoja([_comprobante("PEN", 1180.0)])
        assert "S/" in hoja["S14"].number_format
        assert "US$" not in hoja["S14"].number_format

    def test_una_fila_en_dolares_lleva_el_simbolo_de_dolares(self):
        hoja = _hoja([_comprobante("USD", 149600.0, 3.387)])
        assert "US$" in hoja["S14"].number_format

    def test_el_simbolo_va_por_fila_no_por_columna(self):
        # Es lo que hacía falta: en la misma columna conviven las dos monedas.
        hoja = _hoja([_comprobante("PEN", 1180.0), _comprobante("USD", 149600.0, 3.387)])
        assert "S/" in hoja["S14"].number_format
        assert "US$" in hoja["S15"].number_format

    def test_una_moneda_desconocida_no_inventa_simbolo(self):
        hoja = _hoja([_comprobante("EUR", 100.0)])
        formato = hoja["S14"].number_format
        assert "S/" not in formato and "US$" not in formato
        assert "#,##0.00" in formato

    def test_el_tipo_de_cambio_no_lleva_simbolo_de_moneda(self):
        # No es dinero: es una tasa, y la plantilla la declara (10,4).
        hoja = _hoja([_comprobante("USD", 149600.0, 3.387)])
        assert "US$" not in hoja["W14"].number_format
        assert hoja["W14"].value == 3.387

    def test_los_importes_se_guardan_redondeados(self):
        # El formato sólo redondea lo que se ve; el valor crudo reaparecía en
        # la barra de fórmulas y al reexportar.
        hoja = _hoja([_comprobante("USD", 149600.0, 3.387)])
        assert hoja["J14"].value == 126779.66


class TestPieDeTotales:
    def test_con_una_sola_moneda_el_pie_es_una_suma_simple(self):
        hoja = _hoja([_comprobante("PEN", 1180.0)] * 2)
        assert hoja["A16"].value == "TOTAL S/"
        assert hoja["S16"].value == "=SUM(S14:S15)"

    def test_con_dos_monedas_hay_un_pie_por_cada_una(self):
        # Sumar soles y dólares en la misma celda daba un número sin sentido.
        hoja = _hoja([_comprobante("PEN", 1180.0), _comprobante("USD", 149600.0, 3.387)])
        assert hoja["A16"].value == "TOTAL S/"
        assert hoja["A17"].value == "TOTAL US$"
        assert hoja["S16"].value == '=SUMIF($AB$14:$AB$15,"S",S14:S15)'
        assert hoja["S17"].value == '=SUMIF($AB$14:$AB$15,"D",S14:S15)'

    def test_cada_pie_lleva_el_simbolo_de_su_moneda(self):
        hoja = _hoja([_comprobante("PEN", 1180.0), _comprobante("USD", 149600.0, 3.387)])
        assert "S/" in hoja["S16"].number_format
        assert "US$" in hoja["S17"].number_format

    def test_una_moneda_sin_pie_se_declara_en_vez_de_desaparecer(self):
        hoja = _hoja([_comprobante("PEN", 1180.0), _comprobante("EUR", 100.0)])
        rotulos = [hoja[f"A{fila}"].value for fila in (16, 17)]
        assert "TOTAL S/" in rotulos
        assert any("EUR" in str(r) for r in rotulos)

    def test_en_ventas_el_pie_mira_su_propia_columna_de_moneda(self):
        # En la hoja de ventas la moneda es la V, no la AB.
        hoja = _hoja(
            [_comprobante("PEN", 1180.0), _comprobante("USD", 149600.0, 3.387)],
            Libro.VENTAS,
        )
        assert hoja["P16"].value == '=SUMIF($V$14:$V$15,"S",P14:P15)'
