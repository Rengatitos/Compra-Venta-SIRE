from datetime import date, datetime
from decimal import Decimal

import pytest

from app.domain.catalogos import TIPO_COMPROBANTE, TIPO_DOC_IDENTIDAD
from app.domain.comprobante import (
    Comprobante,
    Libro,
    Origen,
    es_contraparte_generica,
    montos_iguales,
    normalizar_documento,
    normalizar_fecha,
    normalizar_monto,
    normalizar_numero,
    normalizar_serie,
    normalizar_tipo_cp,
)


class TestNormalizarSerie:
    def test_relleno_con_ceros_converge(self):
        # Contasis guarda 00B001 donde el SIRE reporta B001.
        assert normalizar_serie("00B001") == normalizar_serie("B001")
        assert normalizar_serie("00EB01") == normalizar_serie("EB01")

    def test_typo_de_ceros_converge(self):
        # RC CORPORACION, hoja MAYO: 0S898 contra 00S898 en el resto del archivo.
        assert normalizar_serie("0S898") == normalizar_serie("00S898")

    def test_typo_de_caracter_no_converge(self):
        # Mismo archivo: 005060 fue tipeado donde debía decir 00S060. La `S`
        # se escribió como `5`, y eso el motor no puede ni debe adivinarlo.
        assert normalizar_serie("005060") != normalizar_serie("00S060")

    def test_limpia_separadores_y_espacios(self):
        assert normalizar_serie("  f-001 ") == "F001"

    @pytest.mark.parametrize("vacio", ["", None, "-", "#N/A"])
    def test_valores_vacios(self, vacio):
        assert normalizar_serie(vacio) == ""

    def test_serie_toda_ceros_no_colapsa(self):
        assert normalizar_serie("0000") == "0"


class TestNormalizarNumero:
    def test_quita_ceros_a_la_izquierda(self):
        assert normalizar_numero("0000123") == "123"

    def test_float_de_openpyxl_no_arrastra_decimal(self):
        # openpyxl devuelve 116472.0 para una celda numérica.
        assert normalizar_numero(116472.0) == "116472"

    def test_numero_alfanumerico_se_conserva(self):
        assert normalizar_numero("A0012") == "A0012"


class TestNormalizarDocumento:
    def test_deja_solo_digitos(self):
        assert normalizar_documento("20432405525") == "20432405525"

    def test_limpia_caracteres_invisibles(self):
        # En los archivos reales aparecen RUCs con un espacio duro pegado.
        assert normalizar_documento("20432405525\xa0") == "20432405525"

    def test_guion_del_sire_es_vacio(self):
        assert normalizar_documento("-") == ""


class TestNormalizarTipoCp:
    def test_entero_de_openpyxl_se_rellena(self):
        assert normalizar_tipo_cp(1) == "01"

    def test_texto_ya_normalizado(self):
        assert normalizar_tipo_cp("03") == "03"

    def test_codigo_alfabetico_se_conserva(self):
        assert normalizar_tipo_cp("ch") == "CH"


class TestNormalizarMonto:
    def test_cuantiza_a_dos_decimales(self):
        # Contasis guarda el total dividido entre 1.18 sin redondear; el SIRE
        # reporta 44.07. Con float y == esto nunca cuadra.
        assert normalizar_monto(44.067796610169495) == Decimal("44.07")

    def test_separador_de_miles_estilo_ingles(self):
        assert normalizar_monto("1,234.56") == Decimal("1234.56")

    def test_separador_de_miles_estilo_europeo(self):
        assert normalizar_monto("1.234,56") == Decimal("1234.56")

    @pytest.mark.parametrize("vacio", ["", None, "-", "#N/A"])
    def test_valores_vacios_son_cero(self, vacio):
        assert normalizar_monto(vacio) == Decimal("0.00")

    def test_tolerancia_absorbe_el_redondeo(self):
        assert montos_iguales(Decimal("44.07"), Decimal("44.06"))
        assert not montos_iguales(Decimal("44.07"), Decimal("44.09"))


class TestNormalizarFecha:
    def test_datetime_de_openpyxl(self):
        assert normalizar_fecha(datetime(2026, 6, 1)) == date(2026, 6, 1)

    def test_iso_del_sire(self):
        assert normalizar_fecha("2026-06-01T00:00:00") == date(2026, 6, 1)

    def test_formato_peruano(self):
        assert normalizar_fecha("01/06/2026") == date(2026, 6, 1)

    def test_texto_no_reconocible(self):
        assert normalizar_fecha("no es fecha") is None


class TestContraparteGenerica:
    def test_boleta_al_publico(self):
        # Contasis escribe 11111111; el SIRE trae "-", que normaliza a vacío.
        assert es_contraparte_generica("11111111")
        assert es_contraparte_generica(normalizar_documento("-"))

    def test_ruc_real_no_es_generico(self):
        assert not es_contraparte_generica("20608997106")


class TestComprobante:
    def _construir(self, **kwargs):
        base = {
            "libro": Libro.COMPRAS,
            "origen": Origen.SIRE,
            "tipo_cp": 1,
            "serie": "00F001",
            "numero": "0000123",
            "fecha_emision": "2026-06-01",
            "total": 118.0,
        }
        base.update(kwargs)
        return Comprobante(**base)

    def test_normaliza_al_construir(self):
        c = self._construir()
        assert c.tipo_cp == "01"
        assert c.serie == "F001"
        assert c.numero == "123"
        assert c.fecha_emision == date(2026, 6, 1)
        assert c.total == Decimal("118.00")

    def test_serie_numero_es_el_id_del_recurso(self):
        assert self._construir().serie_numero == "F001-123"

    def test_dos_escrituras_de_la_misma_serie_dan_la_misma_clave(self):
        a = self._construir(serie="00F001")
        b = self._construir(serie="F001")
        assert a.clave == b.clave

    def test_fila_basura_no_es_valida(self):
        # RC CORPORACION, hoja AGOSTO, tiene una fila final con #N/A y ceros.
        basura = Comprobante(
            libro=Libro.COMPRAS,
            origen=Origen.SIRE,
            tipo_cp="01",
            serie="",
            numero=0,
            razon_social="#N/A",
        )
        assert not basura.es_valido

    def test_comprobante_completo_es_valido(self):
        assert self._construir().es_valido


class TestCatalogos:
    def test_no_existe_el_codigo_47(self):
        # La tabla del .docx salta de 46 a 48. Transcribirla de corrido
        # desplaza toda la banda siguiente.
        assert "47" not in TIPO_COMPROBANTE
        assert "46" in TIPO_COMPROBANTE
        assert "48" in TIPO_COMPROBANTE

    def test_codigos_faciles_de_perder(self):
        assert TIPO_COMPROBANTE["55"].startswith("BVME")
        assert TIPO_COMPROBANTE["56"].startswith("COMPROBANTE PAGO SEAE")

    def test_codigos_usados_por_los_archivos_reales(self):
        # 01 factura, 03 boleta y 14 recibo de servicios públicos son los que
        # más aparecen en source/REGISTROS CASOS REALES.
        for codigo in ("01", "03", "07", "08", "14"):
            assert codigo in TIPO_COMPROBANTE

    def test_tipos_de_documento_de_identidad(self):
        assert TIPO_DOC_IDENTIDAD["1"].startswith("DNI")
        assert TIPO_DOC_IDENTIDAD["6"].startswith("RUC")
