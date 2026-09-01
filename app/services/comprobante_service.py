from __future__ import annotations

from typing import Any

from app.domain.catalogos import describe_comprobante
from app.repositories._mongo import fecha_desde_bson, monto_a_float

_CAMPOS_MONTO = (
    "base_imponible",
    "igv",
    "exonerado",
    "inafecto",
    "no_gravado",
    "isc",
    "icbper",
    "otros_tributos",
    "total",
)


def serializar_analisis(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
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
        "estado_procesamiento": documento.get("estado_procesamiento", "pendiente"),
        "analisis": serializar_analisis(documento.get("metadata_procesada")),
        "detalle_sunat": documento.get("detalle_sunat", []) or [],
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

    extra = documento.get("extra") or {}
    crudo = extra.get("raw_sire")
    if crudo:
        lineas.append(f"\nDatos crudos de SUNAT:\n{crudo}")

    detalle = documento.get("detalle_sunat")
    if detalle:
        lineas.append(f"\nDetalle de ítems extraído del portal SUNAT:\n{detalle}")

    return "\n".join(lineas)
