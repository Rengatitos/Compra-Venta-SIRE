from __future__ import annotations

import logging
from typing import Any

from app.domain.catalogos import describe_comprobante
from app.repositories._mongo import fecha_desde_bson, monto_a_float

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


def serializar_analisis(metadata: Any) -> dict[str, Any] | None:
    if not metadata:
        return None

    # El análisis lo escribe el modelo, así que su forma no está garantizada.
    # Antes un único documento con una lista en vez de un objeto reventaba la
    # serialización de todo el lote y el listado devolvía un 500.
    if isinstance(metadata, list):
        metadata = next((item for item in metadata if isinstance(item, dict)), None)
        if metadata is None:
            return None
    elif not isinstance(metadata, dict):
        logger.warning(
            "metadata_procesada con tipo inesperado (%s); se ignora el análisis",
            type(metadata).__name__,
        )
        return None

    return {
        "detalle": metadata.get("detalle", []),
        "cuenta_contable": metadata.get("cuenta_contable"),
        "centro_costos": metadata.get("centro_costos"),
        "condicion_igv": metadata.get("condicion_igv"),
        "resultado": metadata.get("resultado"),
        "confianza": metadata.get("confianza"),
        "estado": metadata.get("estado"),
        "documentos": metadata.get("documentos"),
        "descripcion": metadata.get("descripcion"),
        "observaciones": metadata.get("observaciones"),
        "rag": metadata.get("rag"),
    }


def serializar(documento: dict[str, Any]) -> dict[str, Any]:
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
        "analisis": serializar_analisis(documento.get("metadata_procesada")),
        "detalle_sunat": documento.get("detalle_sunat", []) or [],
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


def texto_para_ia(documento: dict[str, Any]) -> str:
    lineas = [
        f"Tipo de comprobante: {documento.get('tipo_cp', '')} - "
        f"{describe_comprobante(documento.get('tipo_cp', ''))}",
        f"Serie-Número: {documento.get('serie_numero', '')}",
        f"Contraparte: {documento.get('documento_contraparte', '')} - "
        f"{documento.get('razon_social', '')}",
        f"Fecha de emisión: {fecha_desde_bson(documento.get('fecha_emision'))}",
        f"Moneda: {documento.get('moneda', 'PEN')}",
        f"Base imponible: {monto_a_float(documento.get('base_imponible'))}",
        f"IGV: {monto_a_float(documento.get('igv'))}",
        f"Exonerado: {monto_a_float(documento.get('exonerado'))}",
        f"Inafecto: {monto_a_float(documento.get('inafecto'))}",
        f"No gravado: {monto_a_float(documento.get('no_gravado'))}",
        f"ICBPER: {monto_a_float(documento.get('icbper'))}",
        f"Total: {monto_a_float(documento.get('total'))}",
    ]

    # La tasa y el reparto por destino son justamente la señal de la que sale
    # `condicion_igv` en la respuesta del modelo. Hasta ahora sólo los veía
    # enterrados en el JSON crudo, donde compiten con cuarenta campos más.
    tasa = monto_a_float(documento.get("porcentaje_igv"))
    if tasa:
        lineas.append(f"Tasa de IGV declarada: {tasa}%")

    desglose = [
        (etiqueta, monto_a_float(documento.get(f"base_imponible_{sufijo}")),
         monto_a_float(documento.get(f"igv_{sufijo}")))
        for etiqueta, sufijo in (
            ("gravadas", "dg"),
            ("gravadas y no gravadas", "dgng"),
            ("no gravadas", "dng"),
        )
    ]
    # Sólo si hay algo que desglosar: cuando todo es DG, repetirlo es ruido.
    if any(base or igv for _, base, igv in desglose[1:]):
        lineas.append("Destino de la adquisición (base / IGV):")
        lineas.extend(f"  - {etiqueta}: {base} / {igv}" for etiqueta, base, igv in desglose)

    extra = documento.get("extra") or {}
    crudo = extra.get("raw_sire")
    if crudo:
        lineas.append(f"\nDatos crudos de SUNAT:\n{crudo}")

    detalle = documento.get("detalle_sunat")
    if detalle:
        lineas.append(f"\nDetalle de ítems extraído del portal SUNAT:\n{detalle}")

    return "\n".join(lineas)
