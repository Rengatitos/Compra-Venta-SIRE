"""Glosa obtenida del detalle SUNAT, independiente de modelos de IA."""

from typing import Any


def obtener_glosa(documento: dict[str, Any]) -> str:
    manual = documento.get("glosa")
    if isinstance(manual, str):
        return manual.strip()[:500]
    descripciones = []
    for item in documento.get("detalle_sunat") or []:
        if not isinstance(item, dict):
            continue
        descripcion = str(item.get("descripcion") or "").strip()
        if descripcion and descripcion not in descripciones:
            descripciones.append(descripcion)
    return " / ".join(descripciones)[:500]
