"""El registro se lleva en soles, como lo hace el contador.

SUNAT devuelve cada comprobante en su moneda, pero los cuatro registros reales
con los que se comparó esta exportación convierten todo a soles: el importe
por el tipo de cambio, el total en dólares aparte en «EQUIVALENTE EN DOLARES
AMERICANOS», la letra `D` en MONEDA y el tipo de cambio sólo en las filas en
moneda extranjera. Antes cada fila conservaba su propia moneda con un símbolo
en el formato de celda y el pie hacía un `SUMIF` por moneda; eso no coincidía
con lo que hace el contador ni con lo que espera Contasis, que es un registro
en una sola moneda.
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


class TestConversionASoles:
    def test_un_comprobante_en_dolares_se_convierte_a_soles(self):
        hoja = _hoja([_comprobante("USD", 149600.0, 3.387)])
        assert hoja["J4"].value == 429402.71
        assert hoja["K4"].value == 77292.49
        assert hoja["S4"].value == 506695.2
        assert "US$" not in hoja["S4"].number_format
        assert "#,##0.00" in hoja["S4"].number_format

    def test_el_total_en_dolares_va_al_equivalente(self):
        hoja = _hoja([_comprobante("USD", 149600.0, 3.387)])
        assert hoja["AC4"].value == 149600.0
        assert hoja["AB4"].value == "D"

    def test_un_comprobante_en_soles_no_lleva_tipo_de_cambio(self):
        # Ya está en soles: no hay nada que declarar en la columna del TC ni
        # en la del equivalente en dólares.
        hoja = _hoja([_comprobante("PEN", 1180.0)])
        assert hoja["W4"].value is None
        assert hoja["AC4"].value is None
        assert hoja["S4"].value == 1180.0

    def test_el_tipo_de_cambio_llega_a_la_columna_w(self):
        hoja = _hoja([_comprobante("USD", 149600.0, 3.387)])
        assert hoja["W4"].value == 3.387

    def test_el_tipo_de_cambio_se_guarda_con_cuatro_decimales(self):
        # La plantilla lo declara "(10,4) NUMERICO": redondear a dos
        # convertía un 3.3871 en 3.39.
        hoja = _hoja([_comprobante("USD", 118.0, 3.3871)])
        assert hoja["W4"].value == 3.3871
        assert hoja["S4"].value == 399.68

    def test_en_ventas_el_equivalente_es_la_columna_w_y_el_tc_la_q(self):
        hoja = _hoja([_comprobante("USD", 149600.0, 3.387)], Libro.VENTAS)
        assert hoja["Q4"].value == 3.387
        assert hoja["W4"].value == 149600.0
        assert hoja["P4"].value == 506695.2


class TestFilaSinTipoDeCambio:
    def test_dolares_sin_tipo_de_cambio_se_deja_nominal_y_marcado(self):
        # No hay con qué convertir: se deja el importe tal cual, con el
        # símbolo de su moneda para que se note que no está en soles.
        hoja = _hoja([_comprobante("USD", 149600.0, 0)])
        assert hoja["S4"].value == 149600.0
        assert "US$" in hoja["S4"].number_format
        assert hoja["AC4"].value == 149600.0
        assert hoja["W4"].value is None

    def test_una_moneda_desconocida_sin_tipo_de_cambio_usa_su_propio_codigo(self):
        hoja = _hoja([_comprobante("EUR", 100.0, 0)])
        assert "EUR" in hoja["S4"].number_format

    def test_una_moneda_desconocida_con_tipo_de_cambio_si_se_convierte(self):
        hoja = _hoja([_comprobante("EUR", 100.0, 3.9)])
        assert hoja["S4"].value == 390.0
        assert "EUR" not in hoja["S4"].number_format
        assert "#,##0.00" in hoja["S4"].number_format

    def test_el_simbolo_es_por_fila_no_por_columna(self):
        # En el mismo registro pueden convivir una fila en soles, una en
        # dólares sin tipo de cambio y otra en dólares que sí se convierte.
        hoja = _hoja([
            _comprobante("PEN", 1180.0),
            _comprobante("USD", 149600.0, 0),
            _comprobante("USD", 149600.0, 3.387),
        ])
        assert "US$" not in hoja["S4"].number_format
        assert "US$" in hoja["S5"].number_format
        assert "US$" not in hoja["S6"].number_format


class TestPieDeTotales:
    def test_el_pie_es_una_unica_suma_del_rango_de_datos(self):
        # Todo el registro está en soles, así que no hace falta un pie por
        # moneda ni un SUMIF condicionado a la columna MONEDA.
        hoja = _hoja([_comprobante("PEN", 1180.0), _comprobante("USD", 149600.0, 3.387)])
        assert hoja["A6"].value == "TOTAL"
        assert hoja["S6"].value == "=SUM(S4:S5)"
        assert "SUMIF" not in str(hoja["S6"].value)
        assert hoja["A7"].value is None
        assert hoja["S6"].number_format == plantilla_excel.FORMATO_IMPORTE

    def test_en_ventas_el_pie_usa_su_propia_columna_de_rotulo(self):
        hoja = _hoja(
            [_comprobante("PEN", 1180.0), _comprobante("USD", 149600.0, 3.387)],
            Libro.VENTAS,
        )
        assert hoja["G6"].value == "TOTAL"
        assert hoja["P6"].value == "=SUM(P4:P5)"
