"""Mapeo de la propuesta del RCE (registro de compras) al modelo canónico.

Los nombres de los campos vienen de respuestas reales de SUNAT. Se dejan tuplas
de candidatos porque no todos los endpoints del SIRE usan el mismo nombre para
el mismo dato; el primero de cada tupla es el que manda el RCE de verdad.
"""

from __future__ import annotations

import json
from typing import Any

from app.domain.comprobante import Comprobante, Libro, Origen
from app.services.sunat.campos import (
    fuente,
    periodo_tributario,
    primero,
    sumar,
    tasa_porcentual,
)

_CAMPOS_SERIE = ("numSerieCDP", "numSerie", "desSerieCDP")
_CAMPOS_NUMERO = ("numCDP", "numComprobante", "numCorrelativo")
_CAMPOS_TIPO_CP = ("codTipoCDP", "codTipoComprobante", "codTipoDocumento")
_CAMPOS_DOC_CONTRAPARTE = ("numDocIdentidadProveedor", "numRucProveedor", "numRuc")
_CAMPOS_TIPO_DOC = ("codTipoDocIdentidadProveedor", "codTipoDocIdentidad")
_CAMPOS_RAZON_SOCIAL = (
    "desRazonSocialProveedor",
    "nomRazonSocialProveedor",
    "desProveedor",
    "desRazonSocialEmisor",
    "nomRazonSocialEmisor",
)
_CAMPOS_FECHA_EMISION = ("fecEmision", "fecEmisionCDP")
# El RCE manda el vencimiento en `fecVencPag`. Con los otros dos nombres el
# campo salía siempre vacío y el Excel acababa repitiendo la fecha de emisión.
_CAMPOS_FECHA_VENCIMIENTO = ("fecVencPag", "fecVencimiento", "fecVcto")
_CAMPOS_MONEDA = ("codMoneda", "desMoneda")
_CAMPOS_TIPO_CAMBIO = ("mtoTipoCambio", "valTipoCambio")
_CAMPOS_TASA_IGV = ("porTasaIGV", "porcTasaIGV", "tasaIGV")

# El RCE reparte la base imponible y el IGV en tres destinos —gravadas (DG),
# gravadas y no gravadas (DGNG) y no gravadas (DNG)— y hay que sumarlos: un
# comprobante puede traer importe en más de uno, así que quedarse con el
# primero perdería el resto. Los `...Original` guardan el valor previo a una
# modificación y no entran en la suma.
_MONTOS_SUMA = {
    "base_imponible": ("mtoBIGravadaDG", "mtoBIGravadaDGNG", "mtoBIGravadaDNG"),
    "igv": ("mtoIgvIpmDG", "mtoIgvIpmDGNG", "mtoIgvIpmDNG"),
}

# El registro de compras pide los tres destinos en columnas separadas, así que
# no basta con la suma de arriba: sin desglosarlos, un comprobante con importe
# en DGNG o DNG se declaraba entero como gravado (el total cuadra, el destino
# no).
_MONTOS_DESTINO = {
    "base_imponible_dg": ("mtoBIGravadaDG",),
    "igv_dg": ("mtoIgvIpmDG",),
    "base_imponible_dgng": ("mtoBIGravadaDGNG",),
    "igv_dgng": ("mtoIgvIpmDGNG",),
    "base_imponible_dng": ("mtoBIGravadaDNG",),
    "igv_dng": ("mtoIgvIpmDNG",),
}

# Los que vienen en un único campo. Se dejan alternativas por si otro endpoint
# del SIRE usa otro nombre, pero el primero de cada tupla es el que manda el
# RCE de verdad.
_MONTOS = {
    # "Valor de las adquisiciones no gravadas": el RCE mete aquí lo exonerado
    # y lo inafecto sin distinguirlos.
    "no_gravado": ("mtoValorAdqNG",),
    "icbper": ("mtoIcbp", "mtoICBPER"),
    "isc": ("mtoISC", "mtoIsc"),
    "otros_tributos": ("mtoOtrosTrib", "mtoOtrosTributos", "mtoOtrosCargos"),
    "total": ("mtoTotalCp", "mtoImporteTotal"),
}


def a_comprobante(registro: dict[str, Any]) -> Comprobante:
    fuente_montos = fuente(registro)

    montos = {
        destino: primero(fuente_montos, candidatos, 0)
        for destino, candidatos in _MONTOS.items()
    }
    montos.update(
        {
            destino: sumar(fuente_montos, campos)
            for destino, campos in _MONTOS_SUMA.items()
        }
    )
    montos.update(
        {
            destino: primero(fuente_montos, campos, 0)
            for destino, campos in _MONTOS_DESTINO.items()
        }
    )

    return Comprobante(
        libro=Libro.COMPRAS,
        origen=Origen.SIRE,
        tipo_cp=primero(registro, _CAMPOS_TIPO_CP),
        serie=primero(registro, _CAMPOS_SERIE),
        numero=primero(registro, _CAMPOS_NUMERO),
        tipo_doc_identidad=primero(registro, _CAMPOS_TIPO_DOC),
        documento_contraparte=primero(registro, _CAMPOS_DOC_CONTRAPARTE),
        razon_social=primero(registro, _CAMPOS_RAZON_SOCIAL),
        fecha_emision=primero(registro, _CAMPOS_FECHA_EMISION, None),
        fecha_vencimiento=primero(registro, _CAMPOS_FECHA_VENCIMIENTO, None),
        moneda=primero(registro, _CAMPOS_MONEDA, "PEN"),
        # Desde `fuente_montos`: el tipo de cambio viene anidado, no en la raíz.
        tipo_cambio=primero(fuente_montos, _CAMPOS_TIPO_CAMBIO, None),
        porcentaje_igv=tasa_porcentual(registro, _CAMPOS_TASA_IGV),
        extra=_extra(registro),
        **montos,
    )


def _extra(registro: dict[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {"raw_sire": json.dumps(registro, ensure_ascii=False)}
    periodo = periodo_tributario(registro)
    if periodo:
        extra["periodo_sunat"] = periodo
    return extra
