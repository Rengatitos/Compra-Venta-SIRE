import json
import logging

logger = logging.getLogger(__name__)


def dedupe_by_reference(invoices: list[dict]) -> list[dict]:
    """Conserva el primer registro por referencia; evita exportar/mostrar duplicados históricos."""
    deduped: list[dict] = []
    seen_refs = set()
    for row in invoices:
        ref = row.get("_ID_REFERENCIA")
        if not ref or ref in seen_refs:
            continue
        seen_refs.add(ref)
        deduped.append(row)
    return deduped


def parse_metadata(row: dict) -> dict:
    """Parsea metadata_procesada de forma segura. Retorna dict vacío si falla."""
    if not row.get("metadata_procesada"):
        return {}
    try:
        meta = row["metadata_procesada"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        if isinstance(meta, dict):
            return meta
        return {}
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("No se pudo parsear metadata_procesada para serie_numero=%s: %s", row.get("serie_numero"), e)
        return {}


def serialize_factura(row: dict) -> dict:
    """Serializa una factura con todos los campos base + metadata."""
    fac = {
        "_ID_REFERENCIA": row.get("serie_numero"),
        "RUC_EMISOR": row.get("ruc_emisor"),
        "NOMBRE_PROVEEDOR": row.get("nombre_proveedor", ""),
        "FECHA_EMISION": row.get("fecha_emision"),
        "TOTAL": row.get("total"),
        "ESTADO": row.get("estado_procesamiento", "pendiente"),
        "RAW_DATA": row.get("raw_data", ""),
        "detalle_compras_sunat": row.get("detalle_compras_sunat", [])
    }
    fac.update(parse_metadata(row))
    return fac
