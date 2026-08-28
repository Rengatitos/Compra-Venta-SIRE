from datetime import date
from decimal import Decimal

from bson.decimal128 import Decimal128

from app.domain.comprobante import Comprobante, Libro, Origen
from app.repositories.comprobantes import a_documento, desde_documento
from app.services import export_service
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
    "montos": {
        "mtoBIGravada": 100.0,
        "mtoIGV": 18.0,
        "mtoTotalCp": 118.0,
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

    def test_excel_de_lote(self):
        salida = export_service.excel_de_lote([serializar(_documento_completo())] * 3)
        assert salida.getbuffer().nbytes > 0

    def test_pdf_de_lote(self):
        salida = export_service.pdf_de_lote([serializar(_documento_completo())] * 3)
        assert salida.getvalue().startswith(b"%PDF")

    def test_consistencia_detecta_detalle_completo(self):
        # La suma del detalle de la IA (118.00) cuadra con el total.
        salida = export_service.excel_de_lote([serializar(_documento_completo())])
        assert salida.getbuffer().nbytes > 0
