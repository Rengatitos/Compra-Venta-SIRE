"""Cuándo dos glosas describen la misma operación.

Base de las clasificaciones frecuentes: un restaurante compra papa y zanahoria
cada semana, y la glosa cambia en detalles que no cambian la cuenta —«SACOS DE
PAPA DE PRIMERA» contra «SACOS DE PAPA», el mes en un recibo de internet—.
Volver a pagar tres llamadas a Gemini por cada una no aporta nada.

La comparación es por conjunto de palabras significativas (sin orden, sin
tildes, sin palabras vacías, meses, años ni números sueltos), con Jaccard.
"""

from __future__ import annotations

import re
import unicodedata

VACIAS = frozenset(
    "DE DEL LA LAS EL LOS Y E O U A AL EN CON POR PARA SIN SU SUS UN UNA UNOS UNAS "
    "X N NRO NO NUM COD CODIGO ITEM ITEMS SEGUN".split()
)
MESES = frozenset(
    "ENERO FEBRERO MARZO ABRIL MAYO JUNIO JULIO AGOSTO SETIEMBRE SEPTIEMBRE OCTUBRE "
    "NOVIEMBRE DICIEMBRE ENE FEB MAR ABR MAY JUN JUL AGO SET SEP OCT NOV DIC".split()
)
_PALABRA = re.compile(r"[A-Z0-9]+")


def palabras(glosa: str | None) -> frozenset[str]:
    """Palabras que identifican la operación."""
    texto = unicodedata.normalize("NFKD", (glosa or "").upper())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return frozenset(
        p for p in _PALABRA.findall(texto)
        if len(p) > 1 and not p.isdigit() and p not in VACIAS and p not in MESES
    )


def clave(glosa: str | None) -> str:
    """Identificador estable de la glosa: sus palabras, ordenadas."""
    return " ".join(sorted(palabras(glosa)))


def similitud(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
