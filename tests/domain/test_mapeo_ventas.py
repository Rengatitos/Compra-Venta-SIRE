"""Mapeo de la propuesta del RVIE al modelo canónico.

El fixture reproduce la forma real de
`/rvie/propuesta/web/propuesta/{periodo}/comprobantes`, con los datos del
cliente anonimizados. Ventas no es compras con otro nombre: los importes vienen
sueltos en la raíz (no hay bloque `montos`), separa exonerado de inafecto,
manda los descuentos en campo aparte, y no trae ni vencimiento ni tasa de IGV.
"""

from datetime import date
from decimal import Decimal

from app.domain.comprobante import Libro, Origen
from app.services.sunat.propuesta import a_comprobante, pertenece_al_periodo

# Boleta electrónica a consumidor final: el grueso del registro de ventas.
PAYLOAD_BOLETA = {
    "id": "6982a2f341c44c660f4d0e37",
    "numRuc": "20603391692",
    # Razón social de la EMPRESA EMISORA, no del cliente. Ver el test de abajo.
    "nomRazonSocial": "EMPRESA QUE EMITE S.R.L.",
    "perPeriodoTributario": "202602",
    "codCar": "2060339169203EB010000000160",
    "codTipoCDP": "03",
    "numSerieCDP": "EB01",
    "numCDP": "160",
    "codTipoCarga": "1",
    "codSituacion": "1",
    # El RVIE manda la fecha en dd/mm/aaaa, no en ISO como el fixture del RCE.
    "fecEmision": "03/02/2026",
    "codTipoDocIdentidad": "1",
    "numDocIdentidad": "44444444",
    "nomRazonSocialCliente": "PEREZ QUISPE, MARIA",
    "mtoValFactExpo": 0.0,
    "mtoBIGravada": 0.0,
    "mtoDsctoBI": 0.0,
    "mtoIGV": 0.0,
    "mtoDsctoIGV": 0.0,
    "mtoExonerado": 400.0,
    "mtoInafecto": 0.0,
    "mtoISC": 0.0,
    "mtoBIIvap": 0.0,
    "mtoIvap": 0.0,
    "mtoIcbp": 0.0,
    "mtoOtrosTrib": 0.0,
    "mtoTotalCP": 400.0,
    "codMoneda": "PEN",
    "mtoTipoCambio": 1,
    "codEstadoComprobante": "1",
    "desEstadoComprobante": "ACTIVO",
    "indOperGratuita": "0",
    "mtoValorOpGratuitas": 0.0,
    "mtoValorFob": 0.0,
    "indTipoOperacion": "0101",
    "mtoPorcParticipacion": 0.0,
    "mtoValorFobDolar": 0.0,
    "documentoMod": [],
}


class TestMapeoDeVentas:
    def test_campos_principales(self):
        c = a_comprobante(PAYLOAD_BOLETA, Libro.VENTAS)
        assert c.libro is Libro.VENTAS
        assert c.origen is Origen.SIRE
        assert c.tipo_cp == "03"
        assert c.serie == "EB01"
        assert c.numero == "160"
        assert c.fecha_emision == date(2026, 2, 3)
        assert c.moneda == "PEN"

    def test_la_contraparte_es_el_cliente_no_la_empresa_emisora(self):
        # El registro trae las dos razones sociales. Tomar `nomRazonSocial`
        # ponía el nombre del propio vendedor como contraparte en todas y cada
        # una de las filas del registro de ventas.
        c = a_comprobante(PAYLOAD_BOLETA, Libro.VENTAS)
        assert c.razon_social == "PEREZ QUISPE, MARIA"
        assert c.documento_contraparte == "44444444"
        assert c.tipo_doc_identidad == "1"

    def test_una_boleta_sin_cliente_sigue_siendo_valida(self):
        # Las boletas a consumidor final pueden venir sin documento.
        payload = {**PAYLOAD_BOLETA, "numDocIdentidad": "-", "codTipoDocIdentidad": "-"}
        c = a_comprobante(payload, Libro.VENTAS)
        assert c.documento_contraparte == ""
        assert c.es_valido

    def test_importes_sueltos_en_la_raiz_sin_bloque_montos(self):
        c = a_comprobante(PAYLOAD_BOLETA, Libro.VENTAS)
        assert c.exonerado == Decimal("400.00")
        assert c.total == Decimal("400.00")
        assert c.base_imponible == Decimal("0.00")
        assert c.igv == Decimal("0.00")

    def test_los_descuentos_se_restan(self):
        # `mtoDsctoBI` y `mtoDsctoIGV` llegan en positivo: sin restarlos, la
        # base y el IGV de una venta con descuento salen por encima de lo
        # declarado. El nombre del descuento de IGV es `mtoDsctoIGV`, no el
        # `mtoDsctoIgvIpm` que parecía natural por simetría con el RCE.
        payload = {
            **PAYLOAD_BOLETA,
            "mtoBIGravada": 44.07,
            "mtoIGV": 7.93,
            "mtoDsctoBI": 4.07,
            "mtoDsctoIGV": 0.93,
        }
        c = a_comprobante(payload, Libro.VENTAS)
        assert c.base_imponible == Decimal("40.00")
        assert c.igv == Decimal("7.00")

    def test_exonerado_e_inafecto_van_por_separado(self):
        # A diferencia del RCE, que los agrupa en "adquisiciones no gravadas".
        payload = {**PAYLOAD_BOLETA, "mtoExonerado": 100.0, "mtoInafecto": 25.0}
        c = a_comprobante(payload, Libro.VENTAS)
        assert c.exonerado == Decimal("100.00")
        assert c.inafecto == Decimal("25.00")
        assert c.no_gravado == Decimal("0.00")

    def test_el_ivap_entra_en_otros_tributos(self):
        payload = {**PAYLOAD_BOLETA, "mtoOtrosTrib": 3.0, "mtoIvap": 2.0}
        assert a_comprobante(payload, Libro.VENTAS).otros_tributos == Decimal("5.00")

    def test_el_tipo_de_cambio_llega_desde_la_raiz(self):
        payload = {**PAYLOAD_BOLETA, "mtoTipoCambio": 3.75}
        assert a_comprobante(payload, Libro.VENTAS).tipo_cambio == Decimal("3.75")

    def test_el_rvie_no_trae_vencimiento_ni_tasa(self):
        # No es un fallo del mapeo: esos campos no existen en la respuesta.
        # La tasa en `None` hace que la exportación caiga en la general, y sólo
        # si el comprobante tiene IGV.
        c = a_comprobante(PAYLOAD_BOLETA, Libro.VENTAS)
        assert c.fecha_vencimiento is None
        assert c.porcentaje_igv is None

    def test_guarda_los_conceptos_propios_del_rvie_en_extra(self):
        extra = a_comprobante(PAYLOAD_BOLETA, Libro.VENTAS).extra
        assert extra["car_sunat"] == "2060339169203EB010000000160"
        assert extra["tipo_operacion"] == "0101"
        assert extra["estado_comprobante"] == "1"
        assert "PEREZ QUISPE" in extra["raw_sire"]

    def test_la_referencia_de_una_nota_de_credito_se_conserva(self):
        payload = {
            **PAYLOAD_BOLETA,
            "codTipoCDP": "07",
            "documentoMod": [{"codTipoCDP": "03", "numSerieCDP": "EB01", "numCDP": "160"}],
        }
        extra = a_comprobante(payload, Libro.VENTAS).extra
        assert extra["documentos_modificados"][0]["numCDP"] == "160"

    def test_sin_nota_de_credito_no_se_guarda_la_lista_vacia(self):
        assert "documentos_modificados" not in a_comprobante(PAYLOAD_BOLETA, Libro.VENTAS).extra

    def test_filtro_de_periodo(self):
        c = a_comprobante(PAYLOAD_BOLETA, Libro.VENTAS)
        assert pertenece_al_periodo(c, "202602")
        assert not pertenece_al_periodo(c, "202601")

    def test_no_se_confunde_con_el_mapeo_de_compras(self):
        # Los nombres del RCE no aparecen en el RVIE: si el despacho por libro
        # se cruzara, los importes saldrían en cero sin que nada fallara.
        del_rce = {k: v for k, v in PAYLOAD_BOLETA.items() if k != "mtoBIGravada"}
        del_rce["montos"] = {"mtoBIGravadaDG": 44.07}
        assert a_comprobante(del_rce, Libro.VENTAS).base_imponible == Decimal("0.00")
