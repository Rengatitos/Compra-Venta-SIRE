from __future__ import annotations

import logging
from math import isfinite
from typing import Any

from app.domain.catalogos import describe_comprobante
from app.domain.comprobante import normalizar_numero, normalizar_serie, normalizar_tipo_cp
from app.repositories._mongo import fecha_desde_bson, monto_a_float
from app.services.glosa import estado_glosa, observacion_glosa, obtener_glosa
from app.services.revision_comprobantes import de_baja
from app.services.sunat.campos import fuente, raw_sire
from app.services.sunat.contraparte import completar

logger = logging.getLogger(__name__)

_CAMPOS_MONTO = (
    "base_imponible",
    "igv",
    "base_imponible_dg",
    "igv_dg",
    "base_imponible_dgng",
    "igv_dgng",
    "base_imponible_dng",
    "igv_dng",
    "exonerado",
    "inafecto",
    "no_gravado",
    "isc",
    "icbper",
    "otros_tributos",
    "total",
)


def _tiene_detraccion(documento: dict[str, Any]) -> bool:
    """Lee la marca de la propuesta conservada, incluidos registros anteriores."""
    return raw_sire(documento).get("indDetraccion") == "D"


def _tipo_cambio(documento: dict[str, Any]) -> float:
    actual = monto_a_float(documento.get("tipo_cambio"))
    if isfinite(actual) and actual > 0:
        return actual
    actual = actual if isfinite(actual) else 0.0
    moneda = documento.get("moneda", "PEN")
    if documento.get("origen") != "sire" or moneda == "PEN":
        return actual

    # Los documentos antiguos pueden conservar el TC anidado en la respuesta
    # original aunque el mapeo de entonces no lo guardara en el campo canónico.
    # Sólo se recupera el TC de esa fila; sus importes y Mongo no se modifican.
    crudo = raw_sire(documento)
    moneda_cruda = crudo.get("codMoneda") or crudo.get("desMoneda")
    if moneda_cruda and str(moneda_cruda).strip().upper() != str(moneda).strip().upper():
        return actual
    for campo, aliases, normalizar in (
        ("tipo_cp", ("codTipoCDP", "codTipoComprobante", "codTipoDocumento"), normalizar_tipo_cp),
        ("serie", ("numSerieCDP", "numSerie", "desSerieCDP"), normalizar_serie),
        ("numero", ("numCDP", "numComprobante", "numCorrelativo"), normalizar_numero),
    ):
        valor_crudo = next(
            (crudo[alias] for alias in aliases if crudo.get(alias) not in (None, "")), None
        )
        if documento.get(campo) and valor_crudo is not None:
            if normalizar(documento[campo]) != normalizar(valor_crudo):
                return actual
    datos = fuente(crudo)
    for campo in ("mtoTipoCambio", "valTipoCambio"):
        valor = datos.get(campo)
        if isinstance(valor, bool):
            continue
        candidato = monto_a_float(valor)
        if isfinite(candidato) and candidato > 0:
            return candidato
    return actual


def serializar(documento: dict[str, Any]) -> dict[str, Any]:
    documento = completar(documento)
    documento.update({
        campo: valor for campo, valor in (documento.get("contraparte_manual") or {}).items()
        if campo in ("razon_social", "documento_contraparte")
    })
    tipo_cp = documento.get("tipo_cp", "")
    salida: dict[str, Any] = {
        "serie_numero": documento.get("serie_numero", ""),
        "libro": documento.get("libro", ""),
        "origen": documento.get("origen", ""),
        "tipo_cp": tipo_cp,
        "tipo_cp_descripcion": describe_comprobante(tipo_cp),
        "serie": documento.get("serie", ""),
        "numero": documento.get("numero", ""),
        "tipo_doc_identidad": documento.get("tipo_doc_identidad", ""),
        "documento_contraparte": documento.get("documento_contraparte", ""),
        "razon_social": documento.get("razon_social", ""),
        "fecha_emision": fecha_desde_bson(documento.get("fecha_emision")),
        "fecha_vencimiento": fecha_desde_bson(documento.get("fecha_vencimiento")),
        "moneda": documento.get("moneda", "PEN"),
        "tipo_cambio": _tipo_cambio(documento),
        # Sin `or None` un comprobante sin tasa saldría al Excel como 0 %.
        "porcentaje_igv": monto_a_float(documento.get("porcentaje_igv")) or None,
        "estado_procesamiento": documento.get("estado_procesamiento", "pendiente"),
        "analisis": None,
        "glosa": obtener_glosa(documento),
        "observacion": observacion_glosa(documento),
        "de_baja_sunat": de_baja(documento),
        # Con glosa / sin glosa / en evaluación / pendiente, según el tipo de
        # comprobante y si ya se consultó el portal. Lo lee el listado, el
        # Excel y el reporte asociado.
        "estado_glosa": estado_glosa(documento),
        "leyenda_sunat": [
            linea for linea in documento.get("leyenda_sunat") or [] if isinstance(linea, str)
        ],
        "detalle_sunat": documento.get("detalle_sunat", []) or [],
        "detraccion": _tiene_detraccion(documento),
        "detracciones": documento.get("detracciones") or [],
        "detracciones_consultado_en": documento.get("detracciones_consultado_en"),
        # Lo escribe el trabajo de descarga (`pdf_service`). Va aquí para que
        # la pantalla de auditoría sepa qué comprobantes siguen sin respaldo
        # sin tener que consultar el disco.
        "pdf_sunat": documento.get("pdf_sunat") or None,
        # Referencia al comprobante que modifica una nota de crédito o débito.
        # Sólo el RVIE la manda (ver `extra.documentos_modificados` en
        # `app/services/sunat/rvie.py`); la usa la exportación a Excel para
        # llenar las columnas de referencia que antes quedaban vacías.
        "documentos_modificados": [
            item
            for item in (documento.get("extra") or {}).get("documentos_modificados") or []
            if isinstance(item, dict)
        ],
        # Lo escribe el clasificador contable; la exportación a Excel toma de
        # aquí la cuenta base.
        "clasificacion_contable": documento.get("clasificacion_contable") or None,
        # No se guarda en la fila: lo agrega `pagos_vouchers.adjuntar_pagos`, a
        # veces antes de serializar (el reporte y asociado).
        "pagos": documento.get("pagos") or [],
    }
    for campo in _CAMPOS_MONTO:
        salida[campo] = monto_a_float(documento.get(campo))
    return salida


def serializar_lote(documentos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [serializar(documento) for documento in documentos]
