"""Helpers compartidos por los mapeos del RCE y del RVIE."""

from __future__ import annotations

from decimal import Decimal

from app.services.sunat.campos import tasa_porcentual

CAMPOS = ("porTasaIGV", "tasaIGV")


class TestTasaPorcentual:
    def test_convierte_la_fraccion_a_puntos(self):
        assert tasa_porcentual({"porTasaIGV": 0.18}, CAMPOS) == Decimal("18.00")

    def test_la_tasa_de_selva_tambien(self):
        assert tasa_porcentual({"porTasaIGV": 0.105}, CAMPOS) == Decimal("10.500")

    def test_una_tasa_ya_en_puntos_no_se_multiplica(self):
        # El x100 asume que SUNAT manda una fracción, y eso no está confirmado
        # para el RVIE. Sin este guard, un 18 que ya viniera en puntos
        # escribiría 1800 en la columna de tasa del Excel.
        assert tasa_porcentual({"porTasaIGV": 18}, CAMPOS) == Decimal("18")
        assert tasa_porcentual({"porTasaIGV": "10.5"}, CAMPOS) == Decimal("10.5")

    def test_sin_tasa_devuelve_none(self):
        # None, no la tasa general: inventarla falsearía los comprobantes no
        # gravados y los del régimen de selva.
        assert tasa_porcentual({}, CAMPOS) is None

    def test_una_tasa_en_cero_no_es_una_tasa(self):
        assert tasa_porcentual({"porTasaIGV": 0}, CAMPOS) is None

    def test_un_valor_ilegible_no_revienta_el_mapeo(self):
        assert tasa_porcentual({"porTasaIGV": "s/n"}, CAMPOS) is None

    def test_recorre_los_nombres_candidatos(self):
        assert tasa_porcentual({"tasaIGV": 0.18}, CAMPOS) == Decimal("18.00")
