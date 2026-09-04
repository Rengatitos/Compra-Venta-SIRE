"""La columna comparable del reporte.

Este cálculo ya se rompió una vez de la peor forma posible: leía un campo
`importe` que las líneas del portal no tienen, y como `float(None or 0)` no
falla, devolvía 0,00 para todo comprobante con detalle. El resultado era que los
once comparables de un periodo real salían los once descuadrados, cada uno por
su importe completo. Un reporte que acusa de descuadre a todo es peor que no
tener reporte, así que el nombre del campo va cubierto por tests.
"""

from __future__ import annotations

from app.api.v1.routes.auditoria import (
    FUENTE_PDF,
    FUENTE_PORTAL,
    FUENTE_PROPUESTA,
    _a_numero,
    _fuentes,
    _importe_del_detalle,
)

# Líneas reales guardadas por el scraper, con los nombres de columna que les
# pone `_parsear_filas` y los formatos que trae el popup.
DETALLE_REAL = [
    {
        "cantidad": "0.50",
        "unidad_medida": "UNIDAD",
        "codigo": "0100",
        "descripcion": "COCA COLA VR 1.5L X08 RF@#@ -4 @#@33.34@#@.00",
        "valor_unitario": "33.34",
        "precio_unitario": "33.34",
        "valor_venta": "16.67",
        "icbper": "0.00",
    },
    {
        "cantidad": "0.50",
        "unidad_medida": "UNIDAD",
        "codigo": "0098",
        "descripcion": "INCA KOLA VR 1.5L X08 RF 2.0@#@ -4 @#@33.34@#@.00",
        "valor_unitario": "33.34",
        "precio_unitario": "33.34",
        "valor_venta": "16.67",
        "icbper": "0.00",
    },
]


class TestNumero:
    def test_lee_los_formatos_del_popup(self):
        assert _a_numero("16.67") == 16.67
        assert _a_numero(".00") == 0.0
        assert _a_numero("1,234.56") == 1234.56
        assert _a_numero(" 33.34 ") == 33.34

    def test_una_celda_que_no_es_numero_no_cuenta_como_cero(self):
        # Devolver 0.0 aquí es lo que hacía que un detalle ilegible pareciera un
        # comprobante de importe cero.
        assert _a_numero("") is None
        assert _a_numero(None) is None
        assert _a_numero("UNIDAD") is None


class TestImporteDelDetalle:
    def test_suma_la_columna_valor_venta(self):
        assert _importe_del_detalle(DETALLE_REAL) == 33.34

    def test_no_confunde_ausencia_de_detalle_con_importe_cero(self):
        # Es la distinción que sostiene todo el reporte: sin detalle no se
        # cuadra ni se descuadra, falta el dato.
        assert _importe_del_detalle([]) is None
        assert _importe_del_detalle(None) is None

    def test_un_detalle_sin_ninguna_columna_de_importe_no_vale_cero(self):
        # El caso exacto del bug: líneas presentes, campo inexistente.
        sin_importe = [{"descripcion": "ALGO", "cantidad": "1"}]

        assert _importe_del_detalle(sin_importe) is None

    def test_una_linea_ilegible_no_arrastra_a_las_demas(self):
        mezclado = [*DETALLE_REAL, {"valor_venta": "no es un número"}]

        assert _importe_del_detalle(mezclado) == 33.34

    def test_ignora_lo_que_no_sea_una_linea(self):
        assert _importe_del_detalle([*DETALLE_REAL, "basura", None]) == 33.34

    def test_redondea_a_dos_decimales(self):
        tercios = [{"valor_venta": "0.333"}, {"valor_venta": "0.333"}]

        assert _importe_del_detalle(tercios) == 0.67


class TestFuentes:
    def test_un_comprobante_recien_sincronizado_solo_tiene_la_propuesta(self):
        assert _fuentes({"origen": "sire"}) == [FUENTE_PROPUESTA]

    def test_el_detalle_y_el_pdf_se_suman_a_medida_que_se_recolectan(self):
        completo = {
            "origen": "sire",
            "detalle_sunat": DETALLE_REAL,
            "pdf_sunat": {"ruta": "x/compras/2026/06/facturas/F001-1.pdf"},
        }

        assert _fuentes(completo) == [FUENTE_PROPUESTA, FUENTE_PORTAL, FUENTE_PDF]

    def test_un_pdf_sin_ruta_no_cuenta_como_fuente(self):
        assert _fuentes({"origen": "sire", "pdf_sunat": {}}) == [FUENTE_PROPUESTA]

    def test_un_comprobante_de_contasis_no_viene_de_la_propuesta(self):
        # Cuando entre el parser de Contasis, sus comprobantes no pueden citar
        # la propuesta del SIRE como fuente: no salieron de ahí.
        assert _fuentes({"origen": "contasis"}) == []
