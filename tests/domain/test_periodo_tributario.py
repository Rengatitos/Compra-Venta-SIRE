"""El periodo de un comprobante lo decide SUNAT, no su fecha de emisión.

Una factura emitida en julio puede anotarse en el registro de agosto —el
crédito fiscal del IGV no caduca ese mismo mes—, y SUNAT la devuelve en la
propuesta de agosto con `perTributario=202608`. Filtrar por el mes de emisión
la descartaba: en un periodo real eran 27 de 87 compras, S/ 3.101,89.
"""

from app.domain.comprobante import Libro
from app.services.sunat.propuesta import a_comprobante, pertenece_al_periodo

# Factura de julio que SUNAT asigna al registro de agosto.
COMPRA_DIFERIDA = {
    "numSerieCDP": "F001",
    "numCDP": "52160",
    "codTipoCDP": "01",
    "numDocIdentidadProveedor": "20129646099",
    "nomRazonSocialProveedor": "EL BAUL E.I.R.L.",
    "fecEmision": "2026-07-28",
    "perTributario": "202608",
    "codMoneda": "PEN",
    "montos": {"mtoBIGravadaDG": 241.53, "mtoIgvIpmDG": 43.47, "mtoTotalCp": 285.0},
}

VENTA = {
    "numSerieCDP": "EB01",
    "numCDP": "160",
    "codTipoCDP": "03",
    "numDocIdentidad": "44444444",
    "nomRazonSocialCliente": "PEREZ QUISPE, MARIA",
    "fecEmision": "03/02/2026",
    "perPeriodoTributario": "202602",
    "codMoneda": "PEN",
    "mtoExonerado": 400.0,
    "mtoTotalCP": 400.0,
}


class TestPeriodoTributario:
    def test_una_compra_de_julio_anotada_en_agosto_pertenece_a_agosto(self):
        c = a_comprobante(COMPRA_DIFERIDA, Libro.COMPRAS)
        assert c.fecha_emision.strftime("%Y%m") == "202607"
        assert pertenece_al_periodo(c, "202608")
        assert not pertenece_al_periodo(c, "202607")

    def test_el_periodo_de_sunat_se_conserva_en_extra(self):
        assert a_comprobante(COMPRA_DIFERIDA, Libro.COMPRAS).extra["periodo_sunat"] == "202608"

    def test_en_ventas_manda_per_periodo_tributario(self):
        c = a_comprobante(VENTA, Libro.VENTAS)
        assert c.extra["periodo_sunat"] == "202602"
        assert pertenece_al_periodo(c, "202602")
        assert not pertenece_al_periodo(c, "202603")

    def test_sin_periodo_de_sunat_se_cae_al_mes_de_emision(self):
        # Es lo único que queda si un endpoint dejara de mandar el campo.
        sin_periodo = {k: v for k, v in COMPRA_DIFERIDA.items() if k != "perTributario"}
        c = a_comprobante(sin_periodo, Libro.COMPRAS)
        assert "periodo_sunat" not in c.extra
        assert pertenece_al_periodo(c, "202607")
        assert not pertenece_al_periodo(c, "202608")

    def test_un_periodo_vacio_no_cuenta_como_dato(self):
        c = a_comprobante({**COMPRA_DIFERIDA, "perTributario": "  "}, Libro.COMPRAS)
        assert pertenece_al_periodo(c, "202607")

    def test_sigue_descartando_lo_de_otro_periodo(self):
        # El filtro no desaparece: un comprobante que SUNAT asigna a septiembre
        # no entra en el registro de agosto.
        c = a_comprobante({**COMPRA_DIFERIDA, "perTributario": "202609"}, Libro.COMPRAS)
        assert not pertenece_al_periodo(c, "202608")
