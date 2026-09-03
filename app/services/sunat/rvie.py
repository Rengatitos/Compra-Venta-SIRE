"""Mapeo de la propuesta del RVIE (registro de ventas) al modelo canónico.

Los conceptos salen de una descarga real del SIRE
(`source/REGISTROS CASOS REALES/RCV JOAQUISAN 062026.xlsx`, hoja `Hoja2`), que
trae columnas distintas a las del RCE: el RVIE **sí** separa exonerado de
inafecto, manda los descuentos en columnas aparte y añade exportación, IVAP y
el rango de numeración de las boletas resumidas.

Los nombres JSON no están confirmados contra la API, así que cada concepto
lleva su tupla de candidatos y el registro entero se guarda en
`extra.raw_sire`: si SUNAT usa otro nombre, se re-mapea desde ahí sin volver a
descargar (ver `scripts/recalcular_importes.py`).
"""

from __future__ import annotations

import json
from typing import Any

from app.domain.comprobante import Comprobante, Libro, Origen
from app.services.sunat.campos import (
    fuente,
    monto,
    periodo_tributario,
    primero,
    tasa_porcentual,
)

_CAMPOS_SERIE = ("numSerieCDP", "numSerie")
_CAMPOS_NUMERO = ("numCDP", "numCorrelativo")
# El RVIE no manda hoy el final del rango de una boleta resumida; se deja el
# nombre que usa el RCE por si aparece.
_CAMPOS_NUMERO_FINAL = ("numCDPRangoFinal", "numCdpFinal")
_CAMPOS_TIPO_CP = ("codTipoCDP", "codTipoComprobante")

# La contraparte de una venta es el cliente, y ahí está el campo que hay que
# mirar con cuidado: el registro trae también `nomRazonSocial`, que es la razón
# social **de la propia empresa** que emitió el comprobante. Tomarlo por
# contraparte ponía el nombre del vendedor en las 900 filas del registro de
# ventas. En boletas el cliente puede venir sin documento ("VARIOS CLIENTES");
# `normalizar_documento` lo deja en cadena vacía y el comprobante se guarda.
_CAMPOS_DOC_CONTRAPARTE = ("numDocIdentidad", "numDocIdentidadCliente")
_CAMPOS_TIPO_DOC = ("codTipoDocIdentidad", "codTipoDocIdentidadCliente")
_CAMPOS_RAZON_SOCIAL = ("nomRazonSocialCliente", "desRazonSocialCliente", "desCliente")

_CAMPOS_FECHA_EMISION = ("fecEmision",)
# El RVIE no trae vencimiento: en ventas la columna del registro se rellena con
# la fecha de emisión (ver `_fechas` en plantilla_excel). Se dejan los nombres
# del RCE por si SUNAT lo añade.
_CAMPOS_FECHA_VENCIMIENTO = ("fecVencPag", "fecVencimiento")
_CAMPOS_MONEDA = ("codMoneda", "desMoneda")
_CAMPOS_TIPO_CAMBIO = ("mtoTipoCambio", "valTipoCambio")
# Tampoco manda la tasa de IGV, que el RCE sí trae en `porTasaIGV`. Sin ella el
# comprobante queda con `porcentaje_igv=None` y la exportación cae en la tasa
# general, tenga o no tenga IGV el comprobante.
_CAMPOS_TASA_IGV = ("porTasaIGV", "porcTasaIGV")

_CAMPOS_BI_GRAVADA = ("mtoBIGravada",)
_CAMPOS_DSCTO_BI = ("mtoDsctoBI",)
_CAMPOS_IGV = ("mtoIGV", "mtoIgvIpm")
_CAMPOS_DSCTO_IGV = ("mtoDsctoIGV", "mtoDsctoIgvIpm")
_CAMPOS_OTROS_TRIBUTOS = ("mtoOtrosTrib", "mtoOtrosTributos")
_CAMPOS_IVAP = ("mtoIvap",)

_MONTOS = {
    "exonerado": ("mtoExonerado",),
    "inafecto": ("mtoInafecto",),
    "isc": ("mtoISC", "mtoIsc"),
    "icbper": ("mtoIcbp", "mtoIcbper"),
    "total": ("mtoTotalCP", "mtoTotalCp"),
}

# Conceptos propios del RVIE que no tienen sitio en el modelo común. Se
# guardan en `extra` para que la conciliación y el Excel puedan usarlos sin
# volver a parsear `raw_sire`.
_EXTRAS = {
    "valor_exportacion": ("mtoValFactExpo",),
    "bi_gravada_ivap": ("mtoBIIvap",),
    "car_sunat": ("codCar",),
    "tipo_operacion": ("indTipoOperacion",),
    "estado_comprobante": ("codEstadoComprobante",),
    "operacion_gratuita": ("indOperGratuita",),
    "valor_op_gratuitas": ("mtoValorOpGratuitas",),
    "valor_fob": ("mtoValorFob",),
}

# Documento que modifica una nota de crédito o débito. Llega como lista (vacía
# en la inmensa mayoría de comprobantes), así que no encaja en `_EXTRAS`, que
# resuelve un único valor por nombre candidato.
_CAMPO_DOC_MODIFICADO = "documentoMod"


def a_comprobante(registro: dict[str, Any]) -> Comprobante:
    fuente_montos = fuente(registro)

    montos = {
        destino: primero(fuente_montos, candidatos, 0)
        for destino, candidatos in _MONTOS.items()
    }
    # El RVIE manda los descuentos en positivo y en columna aparte; sin
    # restarlos, la base y el IGV de cualquier venta con descuento salen por
    # encima de lo que declara SUNAT.
    montos["base_imponible"] = monto(fuente_montos, _CAMPOS_BI_GRAVADA) - monto(
        fuente_montos, _CAMPOS_DSCTO_BI
    )
    montos["igv"] = monto(fuente_montos, _CAMPOS_IGV) - monto(
        fuente_montos, _CAMPOS_DSCTO_IGV
    )
    # El IVAP (arroz pilado) es un tributo aparte del IGV: en el registro de
    # ventas de Contasis cae en la misma columna que los otros tributos.
    montos["otros_tributos"] = monto(fuente_montos, _CAMPOS_OTROS_TRIBUTOS) + monto(
        fuente_montos, _CAMPOS_IVAP
    )

    extra: dict[str, Any] = {"raw_sire": json.dumps(registro, ensure_ascii=False)}
    periodo = periodo_tributario(registro)
    if periodo:
        extra["periodo_sunat"] = periodo
    for destino, candidatos in _EXTRAS.items():
        valor = primero(fuente_montos, candidatos, None)
        if valor is not None:
            extra[destino] = valor
    # Las boletas resumidas llegarían como rango; sin el número final no se
    # podría saber cuántos comprobantes cubre la fila. Hoy el RVIE no lo manda.
    numero_final = primero(registro, _CAMPOS_NUMERO_FINAL, None)
    if numero_final is not None:
        extra["numero_final"] = numero_final

    # Referencia al comprobante que modifica una nota de crédito o débito.
    # `plantilla_excel._referencia_modificado` la lee de aquí para llenar las
    # columnas de referencia del registro de ventas.
    modificados = registro.get(_CAMPO_DOC_MODIFICADO)
    if modificados:
        extra["documentos_modificados"] = modificados

    return Comprobante(
        libro=Libro.VENTAS,
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
        # Desde `fuente_montos`: en el RCE el tipo de cambio viaja anidado y no
        # hay motivo para suponer que el RVIE lo mande de otra forma.
        tipo_cambio=primero(fuente_montos, _CAMPOS_TIPO_CAMBIO, None),
        porcentaje_igv=tasa_porcentual(fuente_montos, _CAMPOS_TASA_IGV),
        extra=extra,
        **montos,
    )
