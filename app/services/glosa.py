"""Glosa determinista a partir del detalle SUNAT, y su estado por comprobante."""

import re
from typing import Any

from app.domain.catalogos import (
    SIN_DETALLE_POR_LIBRO,
    TIPOS_CON_DETALLE_SUNAT,
    TIPOS_SIN_DETALLE_SUNAT,
)
from app.domain.comprobante import normalizar_tipo_cp
from app.services.sunat.texto import corregir_codificacion

MAX_GLOSA = 500

# Estados de la glosa de un comprobante. Los cuatro se muestran en el listado y
# en la columna «Estado glosa» del Excel.
ESTADO_CON_GLOSA = "con_glosa"
ESTADO_SIN_GLOSA = "sin_glosa"
ESTADO_EN_EVALUACION = "en_evaluacion"
ESTADO_PENDIENTE = "pendiente"

ETIQUETA_ESTADO_GLOSA = {
    ESTADO_CON_GLOSA: "Con glosa",
    ESTADO_SIN_GLOSA: "Sin glosa",
    ESTADO_EN_EVALUACION: "En evaluación",
    ESTADO_PENDIENTE: "Pendiente",
}

OBSERVACION_SIN_GLOSA = "No se pudo obtener glosa"
OBSERVACION_SIN_DETALLE_SUNAT = "SUNAT no publica el detalle de este tipo de comprobante"
OBSERVACION_EN_EVALUACION = "Tipo de comprobante en evaluación"

# Líneas del recuadro «LEYENDA» que no describen nada: el importe en letras,
# fechas, números de tarjeta enmascarados y siglas sueltas (TD, SAT).
_LEYENDA_NO_DESCRIPTIVA = (
    re.compile(r"^SON\b", re.IGNORECASE),
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),
    re.compile(r"\*"),
    re.compile(r"^[\d\W_]+$"),
)


def _lineas_descriptivas(leyenda: Any) -> list[str]:
    salida: list[str] = []
    for linea in leyenda or []:
        if not isinstance(linea, str):
            continue
        texto = corregir_codificacion(linea).strip()
        if len(texto) <= 3 or any(patron.search(texto) for patron in _LEYENDA_NO_DESCRIPTIVA):
            continue
        if texto not in salida:
            salida.append(texto)
    return salida


def obtener_glosa(documento: dict[str, Any]) -> str:
    """Glosa manual si existe; si no, las descripciones del detalle; si no, la leyenda."""
    manual = documento.get("glosa")
    if isinstance(manual, str):
        return manual.strip()[:MAX_GLOSA]
    descripciones: list[str] = []
    for item in documento.get("detalle_sunat") or []:
        if not isinstance(item, dict):
            continue
        descripcion = corregir_codificacion(str(item.get("descripcion") or "")).strip()
        if descripcion and descripcion not in descripciones:
            descripciones.append(descripcion)
    # Muchas facturas recibidas (comisiones bancarias, por ejemplo) no traen
    # descripción en los ítems y la glosa real está en el recuadro de leyenda.
    if not descripciones:
        descripciones = _lineas_descriptivas(documento.get("leyenda_sunat"))
    return " / ".join(descripciones)[:MAX_GLOSA]


def estado_glosa(documento: dict[str, Any]) -> str:
    if obtener_glosa(documento):
        return ESTADO_CON_GLOSA
    tipo = normalizar_tipo_cp(documento.get("tipo_cp"))
    libro = str(documento.get("libro") or "")
    if tipo in TIPOS_SIN_DETALLE_SUNAT or tipo in SIN_DETALLE_POR_LIBRO.get(libro, ()):
        return ESTADO_SIN_GLOSA
    # Sin tipo no hay nada que evaluar: se trata como consultable, igual que
    # una factura. Un código que sí llega y no está en el catálogo, sí queda
    # en evaluación.
    if tipo and tipo not in TIPOS_CON_DETALLE_SUNAT:
        return ESTADO_EN_EVALUACION
    if documento.get("glosa_consultada") is True:
        return ESTADO_SIN_GLOSA
    return ESTADO_PENDIENTE


def observacion_glosa(documento: dict[str, Any]) -> str:
    estado = estado_glosa(documento)
    if estado == ESTADO_EN_EVALUACION:
        return OBSERVACION_EN_EVALUACION
    if estado != ESTADO_SIN_GLOSA:
        return ""
    tipo = normalizar_tipo_cp(documento.get("tipo_cp"))
    libro = str(documento.get("libro") or "")
    if tipo in TIPOS_SIN_DETALLE_SUNAT or tipo in SIN_DETALLE_POR_LIBRO.get(libro, ()):
        return OBSERVACION_SIN_DETALLE_SUNAT
    return OBSERVACION_SIN_GLOSA
