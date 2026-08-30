from datetime import date
from decimal import Decimal

from bson.decimal128 import Decimal128
from openpyxl import load_workbook

from app.domain.comprobante import Comprobante, Libro, Origen
from app.repositories.comprobantes import a_documento, desde_documento
from app.services import export_service, plantilla_excel
from app.services.comprobante_service import serializar, texto_para_ia
from app.services.sunat.propuesta import (
    a_comprobante,
    pertenece_al_periodo,
    serie_aceptada,
)

PAYLOAD_SIRE = {
    "numSerieCDP": "F001",
    "numCDP": "123",
    "codTipoCDP": "01",
    "numDocIdentidadProveedor": "20129646099",
    "codTipoDocIdentidadProveedor": "6",
    "desRazonSocialProveedor": "ELECTROCENTRO S.A.",
    "fecEmision": "2026-06-15",
    "codMoneda": "PEN",
    # Forma real del bloque `montos` del RCE, capturada de una respuesta de
    # SUNAT. El fixture anterior usaba `mtoBIGravada`/`mtoIGV`, nombres que el
    # SIRE no envía nunca: los tests pasaban mientras en producción la base y
    # el IGV llegaban siempre en cero.
    "montos": {
        "mtoBIGravadaDG": 100.0,
        "mtoIgvIpmDG": 18.0,
        "mtoBIGravadaDGNG": 0.0,
        "mtoIgvIpmDGNG": 0.0,
        "mtoBIGravadaDNG": 0.0,
        "mtoIgvIpmDNG": 0.0,
        "mtoValorAdqNG": 0.0,
        "mtoIcbp": 0.0,
        "mtoOtrosTrib": 0.0,
        "mtoISC": 0.0,
        "mtoIMB": 0.0,
        "mtoTotalCp": 118.0,
        "mtoBIGravadaDGOriginal": None,
        "mtoIgvIpmDGOriginal": None,
    },
}


class TestMapeoDesdeSire:
    def test_campos_principales(self):
        c = a_comprobante(PAYLOAD_SIRE, Libro.COMPRAS)
        assert c.tipo_cp == "01"
        assert c.serie == "F001"
        assert c.numero == "123"
        assert c.documento_contraparte == "20129646099"
        assert c.razon_social == "ELECTROCENTRO S.A."
        assert c.fecha_emision == date(2026, 6, 15)

    def test_montos_salen_del_bloque_anidado(self):
        c = a_comprobante(PAYLOAD_SIRE, Libro.COMPRAS)
        assert c.base_imponible == Decimal("100.00")
        assert c.igv == Decimal("18.00")
        assert c.total == Decimal("118.00")

    def test_suma_los_tres_destinos_de_la_base_y_del_igv(self):
        # El RCE reparte la base y el IGV entre gravadas (DG), gravadas y no
        # gravadas (DGNG) y no gravadas (DNG). Quedarse con el primero que no
        # sea cero perdería los otros dos.
        payload = {
            **PAYLOAD_SIRE,
            "montos": {
                **PAYLOAD_SIRE["montos"],
                "mtoBIGravadaDG": 100.0,
                "mtoBIGravadaDGNG": 30.0,
                "mtoBIGravadaDNG": 20.0,
                "mtoIgvIpmDG": 18.0,
                "mtoIgvIpmDGNG": 5.4,
                "mtoIgvIpmDNG": 3.6,
            },
        }
        c = a_comprobante(payload, Libro.COMPRAS)
        assert c.base_imponible == Decimal("150.00")
        assert c.igv == Decimal("27.00")

    def test_ignora_los_montos_originales(self):
        # `...Original` guarda el valor previo a una modificación; sumarlo
        # duplicaría la base.
        payload = {
            **PAYLOAD_SIRE,
            "montos": {**PAYLOAD_SIRE["montos"], "mtoBIGravadaDGOriginal": 999.0},
        }
        assert a_comprobante(payload, Libro.COMPRAS).base_imponible == Decimal("100.00")

    def test_otros_tributos_usa_el_nombre_del_rce(self):
        payload = {
            **PAYLOAD_SIRE,
            "montos": {**PAYLOAD_SIRE["montos"], "mtoOtrosTrib": 7.5},
        }
        assert a_comprobante(payload, Libro.COMPRAS).otros_tributos == Decimal("7.50")

    def test_conserva_el_json_crudo(self):
        c = a_comprobante(PAYLOAD_SIRE, Libro.COMPRAS)
        assert "ELECTROCENTRO" in c.extra["raw_sire"]

    def test_nombre_del_proveedor_gana_al_del_comprador(self):
        # La respuesta del SIRE trae ambos; tomar el equivocado invierte la
        # contraparte del comprobante.
        payload = {
            **PAYLOAD_SIRE,
            "desRazonSocialEmisor": "EMPRESA COMPRADORA SAC",
        }
        assert a_comprobante(payload, Libro.COMPRAS).razon_social == "ELECTROCENTRO S.A."

    def test_filtro_de_periodo_descarta_meses_vecinos(self):
        # SUNAT devuelve comprobantes de periodos adyacentes en la misma página.
        c = a_comprobante(PAYLOAD_SIRE, Libro.COMPRAS)
        assert pertenece_al_periodo(c, "202606")
        assert not pertenece_al_periodo(c, "202605")

    def test_filtro_de_serie_heredado(self):
        assert serie_aceptada(a_comprobante(PAYLOAD_SIRE, Libro.COMPRAS))
        boleta = a_comprobante({**PAYLOAD_SIRE, "numSerieCDP": "B001"}, Libro.COMPRAS)
        assert not serie_aceptada(boleta)


class TestRoundTripBson:
    def _comprobante(self) -> Comprobante:
        return a_comprobante(PAYLOAD_SIRE, Libro.COMPRAS)

    def test_los_montos_se_guardan_como_decimal128(self):
        documento = a_documento(self._comprobante(), "empresa1", "202606")
        assert isinstance(documento["total"], Decimal128)
        assert isinstance(documento["base_imponible"], Decimal128)

    def test_ida_y_vuelta_conserva_los_valores(self):
        original = self._comprobante()
        recuperado = desde_documento(a_documento(original, "empresa1", "202606"))

        assert recuperado.serie == original.serie
        assert recuperado.numero == original.numero
        assert recuperado.tipo_cp == original.tipo_cp
        assert recuperado.fecha_emision == original.fecha_emision
        assert recuperado.total == original.total
        assert recuperado.igv == original.igv
        assert recuperado.libro is Libro.COMPRAS
        assert recuperado.origen is Origen.SIRE

    def test_el_documento_lleva_serie_numero_derivado(self):
        documento = a_documento(self._comprobante(), "empresa1", "202606")
        assert documento["serie_numero"] == "F001-123"


def _documento_completo() -> dict:
    documento = a_documento(a_comprobante(PAYLOAD_SIRE, Libro.COMPRAS), "empresa1", "202606")
    documento["estado_procesamiento"] = "analizado"
    documento["metadata_procesada"] = {
        "detalle": [
            {
                "producto": "Energía eléctrica",
                "categoria_contable": "Servicios básicos",
                "cantidad": "1",
                "importe": 118.0,
                "razon": "Consumo del local comercial",
            }
        ],
        "cuenta_contable": "6361",
        "resultado": "GASTO",
        "confianza": "95%",
        "observaciones": "Servicio público recurrente",
    }
    return documento


class TestSerializacion:
    def test_los_montos_salen_como_float(self):
        salida = serializar(_documento_completo())
        assert salida["total"] == 118.0
        assert isinstance(salida["total"], float)

    def test_resuelve_la_descripcion_del_tipo(self):
        assert serializar(_documento_completo())["tipo_cp_descripcion"] == "FACTURA"

    def test_expone_el_analisis_con_claves_en_minuscula(self):
        analisis = serializar(_documento_completo())["analisis"]
        assert analisis["resultado"] == "GASTO"
        assert analisis["confianza"] == "95%"

    def test_sin_analisis_devuelve_none(self):
        documento = a_documento(a_comprobante(PAYLOAD_SIRE, Libro.COMPRAS), "e", "202606")
        documento["estado_procesamiento"] = "sire_recibido"
        assert serializar(documento)["analisis"] is None

    def test_texto_para_ia_incluye_lo_normalizado_y_lo_crudo(self):
        texto = texto_para_ia(_documento_completo())
        assert "FACTURA" in texto
        assert "F001-123" in texto
        assert "ELECTROCENTRO" in texto


class TestExportacion:
    def test_excel_de_un_comprobante(self):
        salida = export_service.excel_de_comprobante(serializar(_documento_completo()))
        assert salida.getbuffer().nbytes > 0

    def test_pdf_de_un_comprobante(self):
        salida = export_service.pdf_de_comprobante(serializar(_documento_completo()))
        assert salida.getvalue().startswith(b"%PDF")

    def test_pdf_de_lote(self):
        salida = export_service.pdf_de_lote([serializar(_documento_completo())] * 3)
        assert salida.getvalue().startswith(b"%PDF")


def _documento_ventas() -> dict:
    return a_documento(a_comprobante(PAYLOAD_SIRE, Libro.VENTAS), "empresa1", "202606")


def _hoja(comprobantes: list[dict], libro: Libro):
    salida = plantilla_excel.excel_plantilla(comprobantes, libro)
    wb = load_workbook(salida)
    assert wb.sheetnames == [plantilla_excel.HOJAS[libro]]
    return wb[plantilla_excel.HOJAS[libro]]


class TestPlantillaContasis:
    def test_conserva_los_encabezados_de_la_plantilla(self):
        hoja = _hoja([serializar(_documento_completo())], Libro.COMPRAS)
        assert hoja["A8"].value == "FORMATO REGISTRO DE COMPRAS  - SISTEMA EXPERTO CONTABLE 14.00"
        assert hoja["A10"].value == "FECHA DE EMISION DEL COMPROBANTE DE PAGO O DOCUMENTO"
        assert hoja["C12"].value == "TIPO"
        assert hoja["A13"].value == "dd/mm/yyyy"

    def test_mapeo_de_compras(self):
        hoja = _hoja([serializar(_documento_completo())], Libro.COMPRAS)
        assert hoja["A14"].value.date() == date(2026, 6, 15)
        assert hoja["C14"].value == "01"
        assert hoja["D14"].value == "F001"
        assert hoja["F14"].value == 123
        assert hoja["G14"].value == 6
        assert hoja["H14"].value == 20129646099
        assert hoja["I14"].value == "ELECTROCENTRO S.A."
        assert hoja["J14"].value == 100.0
        assert hoja["K14"].value == 18.0
        assert hoja["S14"].value == 118.0
        assert hoja["AB14"].value == "S"
        assert hoja["AR14"].value == 18

    def test_las_adquisiciones_no_gravadas_llegan_a_la_columna_p(self):
        # El SIRE no separa exonerado de inafecto en compras: manda un único
        # "valor de las adquisiciones no gravadas". La columna P los agrega, y
        # sin contar `no_gravado` salía en cero para toda compra exonerada.
        documento = {**_documento_completo(), "no_gravado": Decimal("59.78")}
        hoja = _hoja([serializar(documento)], Libro.COMPRAS)
        assert hoja["P14"].value == 59.78

    def test_la_columna_p_suma_los_tres_conceptos(self):
        documento = {
            **_documento_completo(),
            "exonerado": Decimal("10.00"),
            "inafecto": Decimal("5.00"),
            "no_gravado": Decimal("20.00"),
        }
        hoja = _hoja([serializar(documento)], Libro.COMPRAS)
        assert hoja["P14"].value == 35.0

    def test_mapeo_de_ventas(self):
        hoja = _hoja([serializar(_documento_ventas())], Libro.VENTAS)
        assert hoja["C14"].value == "01"
        assert hoja["D14"].value == "F001"
        assert hoja["E14"].value == 123
        assert hoja["H14"].value == "ELECTROCENTRO S.A."
        assert hoja["J14"].value == 100.0
        assert hoja["N14"].value == 18.0
        assert hoja["P14"].value == 118.0
        assert hoja["V14"].value == "S"
        assert hoja["AL14"].value == 18

    def test_las_columnas_del_analisis_quedan_vacias(self):
        hoja = _hoja([serializar(_documento_completo())], Libro.COMPRAS)
        # Cuenta contable base imponible / otros tributos / total, y glosa.
        assert [hoja[c + "14"].value for c in ("AF", "AG", "AH", "AS")] == [None] * 4

    def test_el_analisis_no_aparece_en_ninguna_celda(self):
        hoja = _hoja([serializar(_documento_completo())], Libro.COMPRAS)
        textos = [str(c.value) for fila in hoja.iter_rows() for c in fila if c.value is not None]
        for rastro in ("GASTO", "95%", "6361", "Servicio", "Energ"):
            assert not any(rastro in texto for texto in textos), rastro

    def test_pie_de_totales_suma_el_rango_de_datos(self):
        hoja = _hoja([serializar(_documento_completo())] * 3, Libro.COMPRAS)
        assert hoja["A17"].value == "TOTAL"
        assert hoja["S17"].value == "=SUM(S14:S16)"

    def test_sin_comprobantes_salen_solo_los_encabezados(self):
        hoja = _hoja([], Libro.VENTAS)
        assert hoja.max_row == 13
        assert hoja["A10"].value == "FECHA DE EMISION DEL COMPROBANTE DE PAGO O DOCUMENTO"

    def test_las_filas_de_ejemplo_de_la_plantilla_no_sobreviven(self):
        # La plantilla trae `=+A14`, `=+S14/1.18` y una fila TOTAL precargada.
        hoja = _hoja([serializar(_documento_completo())], Libro.COMPRAS)
        formulas = [
            str(c.value)
            for fila in hoja.iter_rows(min_row=14)
            for c in fila
            if isinstance(c.value, str) and c.value.startswith("=")
        ]
        assert all(f.startswith("=SUM(") for f in formulas)
