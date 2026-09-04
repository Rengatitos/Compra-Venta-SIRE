"""Traducción del XML de un comprobante electrónico (UBL 2.1) a las líneas de
detalle que guarda el proyecto.

Es el equivalente de `rce.py`/`rvie.py` para el XML: aquí viven las reglas de
negocio del mapeo y nada más. No sabe qué es HTTP ni Mongo —entra `bytes`, sale
`list[dict]`—, así que se puede probar con un XML de tres líneas escrito a mano.
Eso importa porque el mapeo se construyó sobre el estándar UBL y los catálogos
de SUNAT, no sobre un XML de un contribuyente concreto.

El destino es el mismo contrato que produce el raspado del portal
(`scraping_sunat._COLUMNAS`): exactamente ocho claves, todas `str`, cadena vacía
cuando el dato no está. Lo consumen el reporte de auditoría, el RAG, la
plantilla de Excel y la tabla del frontend, así que la forma no es negociable y
un `None` o un número romperían a alguno de ellos.
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

# Las mismas ocho claves, en el mismo orden, que `scraping_sunat._COLUMNAS`. No
# se importan de allí a propósito: ese módulo arrastra Playwright y esto es un
# mapeador puro. La no-divergencia la fija un test que sí importa los dos y
# compara las tuplas.
CLAVES = (
    "cantidad",
    "unidad_medida",
    "codigo",
    "descripcion",
    "valor_unitario",
    "precio_unitario",
    "valor_venta",
    "icbper",
)

# Un comprobante trae sus líneas bajo un nombre distinto según el tipo:
# factura y boleta usan `InvoiceLine`, la nota de crédito `CreditNoteLine` y la
# de débito `DebitNoteLine`. Buscar los tres cubre los cuatro tipos (01, 03, 07,
# 08) con el mismo código, sin que el mapeador tenga que saber qué se pidió.
NOMBRES_LINEA = ("InvoiceLine", "CreditNoteLine", "DebitNoteLine")

# La cantidad también cambia de nombre con el tipo de documento.
NOMBRES_CANTIDAD = ("InvoicedQuantity", "CreditedQuantity", "DebitedQuantity")

# Catálogo 05 de SUNAT: IGV es 1000, ISC 2000, ICBPER 7152. Hay que filtrar por
# el esquema del tributo y no tomar el primer `TaxSubtotal` de la línea, porque
# si no el importe del IGV acabaría en la columna del ICBPER.
ESQUEMA_ICBPER = "7152"

# Catálogo 16: en `AlternativeConditionPrice`, el 01 es el precio unitario que
# se cobró; el 02 es el valor *referencial* de una operación gratuita. Sólo
# valdría el 01: dar el 02 reportaría como cobrado algo que no se cobró.
PRECIO_UNITARIO_CON_IGV = "01"


class ErrorXmlCpe(Exception):
    """El XML no se puede procesar.

    Se distingue de "el XML no tiene líneas" (que devuelve una lista vacía)
    porque son cosas distintas para quien llama: esto es un artefacto roto y
    aquello un comprobante que hay que resolver por otra vía.
    """


def _local(etiqueta: str) -> str:
    """El nombre del elemento sin el namespace.

    Todo el recorrido se hace por nombre local en vez de por URI. Es lo que
    hace al mapeo inmune al prefijo que use el emisor, a un cambio de versión
    de UBL y a que un OSE sirva el documento con otros namespaces —el tipo de
    sorpresa que se paga cuando se pegan los URI a mano.
    """
    return etiqueta.rsplit("}", 1)[-1]


def _hijos(elemento, nombre: str) -> list:
    return [hijo for hijo in elemento if _local(hijo.tag) == nombre]


def _hijo(elemento, *nombres: str):
    """El primer hijo que case con alguno de los nombres, en ese orden.

    El orden es la preferencia: se usa para los respaldos del mapeo (un código
    de ítem que puede venir en dos elementos distintos).
    """
    if elemento is None:
        return None
    for nombre in nombres:
        for hijo in elemento:
            if _local(hijo.tag) == nombre:
                return hijo
    return None


def _bajar(elemento, *ruta: str):
    """Desciende por una ruta de nombres locales. `None` si se corta."""
    actual = elemento
    for nombre in ruta:
        actual = _hijo(actual, nombre)
        if actual is None:
            return None
    return actual


def _texto(elemento) -> str:
    """El texto del elemento, saneado. Nunca `None`, nunca numérico.

    Colapsa los blancos porque en el XML las descripciones traen saltos de
    línea y tabulaciones, y acaban en una celda de glosa del Excel y en el
    prompt del RAG.

    No se reformatean los números: si SUNAT escribe `33.34` se guarda `"33.34"`
    tal cual. Los cuatro consumidores ya sanean el texto a número por su cuenta,
    y meter una segunda convención numérica aquí no añadiría nada.
    """
    if elemento is None or elemento.text is None:
        return ""
    return " ".join(elemento.text.split())


def _atributo(elemento, nombre: str) -> str:
    if elemento is None:
        return ""
    return " ".join((elemento.get(nombre) or "").split())


def _icbper(linea) -> str:
    """El importe del ICBPER de la línea, o cadena vacía.

    Dentro del `TaxSubtotal` conviven `TaxAmount` (el importe de la línea) y
    `PerUnitAmount` (los céntimos por bolsa). La columna del portal siempre fue
    el importe, así que va `TaxAmount`: `PerUnitAmount` es el que parece
    correcto y no lo es.
    """
    for total in _hijos(linea, "TaxTotal"):
        for subtotal in _hijos(total, "TaxSubtotal"):
            esquema = _bajar(subtotal, "TaxCategory", "TaxScheme")
            if esquema is None:
                continue
            codigo = _texto(_hijo(esquema, "ID"))
            nombre = _texto(_hijo(esquema, "Name")).upper()
            if codigo == ESQUEMA_ICBPER or nombre == "ICBPER":
                return _texto(_hijo(subtotal, "TaxAmount"))
    return ""


def _precio_unitario(linea) -> str:
    """El precio unitario con IGV, o cadena vacía si el XML no lo trae.

    No se calcula a partir del valor de venta y el impuesto: sería inventar un
    número que parece venir del comprobante sin venir de él. Ningún consumidor
    lo suma —el frontend sólo lo muestra—, así que dejarlo vacío es honesto y
    no rompe nada.
    """
    referencia = _hijo(linea, "PricingReference")
    if referencia is None:
        return ""
    for alterno in _hijos(referencia, "AlternativeConditionPrice"):
        if _texto(_hijo(alterno, "PriceTypeCode")) == PRECIO_UNITARIO_CON_IGV:
            return _texto(_hijo(alterno, "PriceAmount"))
    return ""


def _linea_a_detalle(linea) -> dict[str, str]:
    cantidad = _hijo(linea, *NOMBRES_CANTIDAD)
    articulo = _hijo(linea, "Item")

    # El código del ítem es el del vendedor cuando existe; si no, el estándar.
    codigo = _bajar(articulo, "SellersItemIdentification", "ID")
    if codigo is None:
        codigo = _bajar(articulo, "StandardItemIdentification", "ID")

    # Se construye por comprensión sobre CLAVES para que las ocho existan
    # siempre y sean `str` por construcción, no por disciplina de quien edite
    # esto mañana.
    valores = {
        "cantidad": _texto(cantidad),
        "unidad_medida": _atributo(cantidad, "unitCode"),
        "codigo": _texto(codigo),
        "descripcion": _texto(_hijo(articulo, "Description", "Name")),
        "valor_unitario": _texto(_bajar(linea, "Price", "PriceAmount")),
        "precio_unitario": _precio_unitario(linea),
        "valor_venta": _texto(_hijo(linea, "LineExtensionAmount")),
        "icbper": _icbper(linea),
    }
    return {clave: valores[clave] for clave in CLAVES}


def a_detalle(xml: bytes) -> list[dict[str, str]]:
    """Las líneas del comprobante, en el contrato de `_parsear_filas`.

    Devuelve una lista vacía si el XML no tiene ninguna línea legible. Quien
    llama **no debe guardar esa lista vacía**: el criterio de "pendiente de
    detalle" es que el campo no exista (`_filtro_sin_detalle`), así que escribir
    `[]` sacaría al comprobante de la cola para siempre. Cero líneas significa
    "resuélvelo por otra vía".

    Lanza `ErrorXmlCpe` si el XML no se puede parsear.
    """
    if not xml:
        raise ErrorXmlCpe("El XML está vacío")
    try:
        raiz = ElementTree.fromstring(xml)
    except ElementTree.ParseError as fallo:
        raise ErrorXmlCpe(f"El XML no está bien formado: {fallo}") from fallo

    lineas: list = []
    for nombre in NOMBRES_LINEA:
        lineas = _hijos(raiz, nombre)
        if lineas:
            break

    detalle = [_linea_a_detalle(linea) for linea in lineas]

    # Una línea con los ocho campos vacíos no es una línea del comprobante,
    # es ruido de un XML malformado. No se replica el filtro del raspado
    # (primera celda numérica, descripción que no sea una cabecera) porque ese
    # existe para separar ítems de cabeceras y totales en una tabla HTML, y en
    # el XML no hay cabeceras que separar.
    detalle = [linea for linea in detalle if any(linea.values())]

    if not detalle:
        logger.info("El XML del comprobante no trae ninguna línea de detalle")
    return detalle
