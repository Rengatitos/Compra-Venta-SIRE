"""Glosa obtenida del detalle SUNAT, independiente de modelos de IA."""

from typing import Any

from app.services.sunat.texto import corregir_codificacion

OBSERVACION_SIN_GLOSA = "No se pudo obtener glosa"


def observacion_glosa(documento: dict[str, Any]) -> str:
    if documento.get("glosa_consultada") is True and not obtener_glosa(documento):
        return OBSERVACION_SIN_GLOSA
    return ""


def obtener_glosa(documento: dict[str, Any]) -> str:
    manual = documento.get("glosa")
    if isinstance(manual, str):
        return manual.strip()[:500]
    descripciones = []
    for item in documento.get("detalle_sunat") or []:
        if not isinstance(item, dict):
            continue
        descripcion = corregir_codificacion(str(item.get("descripcion") or "")).strip()
        if descripcion and descripcion not in descripciones:
            descripciones.append(descripcion)
    return " / ".join(descripciones)[:500]
