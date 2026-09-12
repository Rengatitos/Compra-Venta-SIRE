from __future__ import annotations

import json
import logging
from typing import Any

from app.domain.catalogos import describe_comprobante
from app.repositories._mongo import fecha_desde_bson, monto_a_float
from app.services.glosa import observacion_glosa, obtener_glosa
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
    extra = documento.get("extra")
    if not isinstance(extra, dict):
        return False
    crudo = extra.get("raw_sire")
    if isinstance(crudo, str):
        try:
            crudo = json.loads(crudo)
        except ValueError:
            return False
    return isinstance(crudo, dict) and crudo.get("indDetraccion") == "D"


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
        "tipo_cambio": monto_a_float(documento.get("tipo_cambio")),
        # Sin `or None` un comprobante sin tasa saldría al Excel como 0 %.
        "porcentaje_igv": monto_a_float(documento.get("porcentaje_igv")) or None,
        "estado_procesamiento": documento.get("estado_procesamiento", "pendiente"),
        "analisis": None,
        "glosa": obtener_glosa(documento),
        "observacion": observacion_glosa(documento),
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
    }
    for campo in _CAMPOS_MONTO:
        salida[campo] = monto_a_float(documento.get(campo))
    return salida


def serializar_lote(documentos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [serializar(documento) for documento in documentos]
