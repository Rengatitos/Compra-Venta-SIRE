"""El detalle que se guarda tiene que salir del XML con la misma forma exacta
que tenía cuando salía de raspar el popup del portal: ocho claves, todas `str`,
cadena vacía cuando falta el dato. El reporte de auditoría suma `valor_venta`,
el RAG lee `descripcion` y la tabla del frontend descarta la fila si no hay
`descripcion` ni `codigo`; un `None` o un número en cualquiera de esos sitios
revienta silenciosamente.

Y dos trampas de UBL que este mapeo tiene que esquivar: el importe del IGV
puede colarse en la columna del ICBPER si no se filtra por esquema de tributo,
y el `AlternativeConditionPrice` de tipo 02 es un valor referencial de una
operación gratuita, no un precio cobrado.
"""

from __future__ import annotations

import pytest

from app.services import scraping_sunat
from app.services.sunat import cpe_xml
from app.services.sunat.cpe_xml import ErrorXmlCpe, a_detalle

# Factura real en miniatura, con los namespaces que trae SUNAT. Dos líneas: la
# primera con ICBPER y precio con IGV, la segunda sin ninguno de los dos.
FACTURA = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>E001-1929</cbc:ID>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="PEN">385.60</cbc:LineExtensionAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="NIU">2.00</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="PEN">207.63</cbc:LineExtensionAmount>
    <cac:PricingReference>
      <cac:AlternativeConditionPrice>
        <cbc:PriceAmount currencyID="PEN">122.50</cbc:PriceAmount>
        <cbc:PriceTypeCode>01</cbc:PriceTypeCode>
      </cac:AlternativeConditionPrice>
    </cac:PricingReference>
    <cac:TaxTotal>
      <cac:TaxSubtotal>
        <cbc:TaxAmount currencyID="PEN">37.37</cbc:TaxAmount>
        <cac:TaxCategory>
          <cac:TaxScheme><cbc:ID>1000</cbc:ID><cbc:Name>IGV</cbc:Name></cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
      <cac:TaxSubtotal>
        <cbc:TaxAmount currencyID="PEN">0.60</cbc:TaxAmount>
        <cbc:PerUnitAmount currencyID="PEN">0.30</cbc:PerUnitAmount>
        <cac:TaxCategory>
          <cac:TaxScheme><cbc:ID>7152</cbc:ID><cbc:Name>ICBPER</cbc:Name></cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item>
      <cbc:Description>RES.S. HYUNDAI SANTA FE 2019-UP
         DEL REF, 14.50 MM</cbc:Description>
      <cac:SellersItemIdentification><cbc:ID>0000022821</cbc:ID></cac:SellersItemIdentification>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="PEN">103.81</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
  <cac:InvoiceLine>
    <cbc:ID>2</cbc:ID>
    <cbc:InvoicedQuantity unitCode="ZZ">1.00</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="PEN">177.97</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Description>SERVICIO DE INSTALACION</cbc:Description>
      <cac:StandardItemIdentification><cbc:ID>51101500</cbc:ID></cac:StandardItemIdentification>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="PEN">177.97</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>
"""

# El mismo comprobante sin un solo namespace. Sirve para fijar que el recorrido
# es por nombre local: si alguien "arregla" el mapeo pegando los URI, esto falla.
SIN_NAMESPACES = b"""<Invoice>
  <InvoiceLine>
    <InvoicedQuantity unitCode="KGM">3.50</InvoicedQuantity>
    <LineExtensionAmount>10.00</LineExtensionAmount>
    <Item><Description>ARROZ</Description>
      <SellersItemIdentification><ID>A-1</ID></SellersItemIdentification></Item>
    <Price><PriceAmount>2.857</PriceAmount></Price>
  </InvoiceLine>
</Invoice>
"""


def test_las_claves_son_las_mismas_que_las_del_raspado():
    """Las dos definiciones no pueden divergir: el consumidor es el mismo."""
    assert cpe_xml.CLAVES == scraping_sunat._COLUMNAS


class TestContrato:
    def test_cada_linea_trae_las_ocho_claves_como_texto(self):
        detalle = a_detalle(FACTURA)

        assert len(detalle) == 2
        for linea in detalle:
            assert tuple(linea) == cpe_xml.CLAVES
            for clave, valor in linea.items():
                assert isinstance(valor, str), f"{clave} no es str: {valor!r}"

    def test_un_dato_ausente_es_cadena_vacia_y_nunca_none(self):
        """La segunda línea no trae ICBPER ni precio con IGV."""
        segunda = a_detalle(FACTURA)[1]

        assert segunda["icbper"] == ""
        assert segunda["precio_unitario"] == ""
        assert None not in segunda.values()

    def test_los_numeros_se_copian_verbatim(self):
        """Reformatear aquí introduciría una segunda convención numérica."""
        primera = a_detalle(FACTURA)[0]

        assert primera["cantidad"] == "2.00"
        assert primera["valor_venta"] == "207.63"
        assert primera["valor_unitario"] == "103.81"

    def test_la_suma_de_valor_venta_cuadra_con_el_total_del_comprobante(self):
        """Es la columna que compara el reporte de auditoría contra `total`."""
        detalle = a_detalle(FACTURA)

        assert sum(float(linea["valor_venta"]) for linea in detalle) == 385.60


class TestMapeo:
    def test_la_unidad_sale_del_atributo_de_la_cantidad(self):
        detalle = a_detalle(FACTURA)

        assert detalle[0]["unidad_medida"] == "NIU"
        assert detalle[1]["unidad_medida"] == "ZZ"

    def test_el_codigo_del_vendedor_manda_y_el_estandar_es_el_respaldo(self):
        detalle = a_detalle(FACTURA)

        assert detalle[0]["codigo"] == "0000022821"
        assert detalle[1]["codigo"] == "51101500"

    def test_la_descripcion_colapsa_los_blancos(self):
        """En el XML viene con saltos de línea y acaba en una celda de Excel."""
        primera = a_detalle(FACTURA)[0]

        assert primera["descripcion"] == "RES.S. HYUNDAI SANTA FE 2019-UP DEL REF, 14.50 MM"

    def test_el_icbper_sale_del_esquema_7152_y_no_del_igv(self):
        """Sin filtrar por esquema, los 37.37 del IGV acabarían en esta columna."""
        primera = a_detalle(FACTURA)[0]

        assert primera["icbper"] == "0.60"

    def test_el_icbper_es_el_importe_y_no_el_valor_por_unidad(self):
        """`PerUnitAmount` (0.30) es el que parece correcto y no lo es."""
        assert a_detalle(FACTURA)[0]["icbper"] != "0.30"

    def test_el_precio_unitario_sale_del_tipo_01(self):
        assert a_detalle(FACTURA)[0]["precio_unitario"] == "122.50"

    def test_un_valor_referencial_de_gratuito_no_cuenta_como_precio(self):
        """El tipo 02 es referencial: darlo diría que se cobró algo que no."""
        gratuito = FACTURA.replace(
            b"<cbc:PriceTypeCode>01</cbc:PriceTypeCode>",
            b"<cbc:PriceTypeCode>02</cbc:PriceTypeCode>",
        )

        assert a_detalle(gratuito)[0]["precio_unitario"] == ""

    def test_no_depende_de_los_namespaces(self):
        detalle = a_detalle(SIN_NAMESPACES)

        assert len(detalle) == 1
        assert detalle[0]["descripcion"] == "ARROZ"
        assert detalle[0]["unidad_medida"] == "KGM"
        assert detalle[0]["codigo"] == "A-1"


class TestOtrosTiposDeDocumento:
    def test_una_nota_de_credito_mapea_igual(self):
        nota = b"""<CreditNote>
          <CreditNoteLine>
            <CreditedQuantity unitCode="NIU">1.00</CreditedQuantity>
            <LineExtensionAmount>50.00</LineExtensionAmount>
            <Item><Description>DEVOLUCION</Description></Item>
            <Price><PriceAmount>50.00</PriceAmount></Price>
          </CreditNoteLine>
        </CreditNote>"""

        detalle = a_detalle(nota)

        assert len(detalle) == 1
        assert detalle[0]["cantidad"] == "1.00"
        assert detalle[0]["descripcion"] == "DEVOLUCION"
        assert detalle[0]["valor_venta"] == "50.00"

    def test_una_nota_de_debito_mapea_igual(self):
        nota = b"""<DebitNote>
          <DebitNoteLine>
            <DebitedQuantity unitCode="NIU">2.00</DebitedQuantity>
            <LineExtensionAmount>15.00</LineExtensionAmount>
            <Item><Description>INTERES MORATORIO</Description></Item>
          </DebitNoteLine>
        </DebitNote>"""

        detalle = a_detalle(nota)

        assert detalle[0]["descripcion"] == "INTERES MORATORIO"
        assert detalle[0]["valor_unitario"] == ""


class TestCasosLimite:
    def test_un_xml_sin_lineas_devuelve_lista_vacia(self):
        """Quien llama nunca debe guardar esto: `[]` saca al comprobante de la
        cola de pendientes para siempre."""
        assert a_detalle(b"<Invoice><ID>F001-1</ID></Invoice>") == []

    def test_una_linea_completamente_vacia_se_descarta(self):
        vacia = b"<Invoice><InvoiceLine><ID>1</ID></InvoiceLine></Invoice>"

        assert a_detalle(vacia) == []

    def test_un_xml_mal_formado_lanza(self):
        with pytest.raises(ErrorXmlCpe):
            a_detalle(b"<Invoice><InvoiceLine>")

    def test_un_xml_vacio_lanza(self):
        with pytest.raises(ErrorXmlCpe):
            a_detalle(b"")
