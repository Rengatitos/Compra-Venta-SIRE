"""Catálogo CIIU Rev. 4 (INEI) para elegir las actividades de una empresa.

El CSV se generó a partir de las «Notas explicativas CIIU Rev. 4» del
conocimiento del clasificador (`app/resources/clasificador/conocimiento/ciiu`):
son las 418 clases con su título. Algunos títulos largos salen cortados donde
el PDF partía la línea; para buscar y reconocer la actividad basta.
"""

from __future__ import annotations

import csv
import unicodedata
from functools import cache
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parents[1] / "resources" / "clasificador" / "ciiu_rev4.csv"


def _plano(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()


@cache
def catalogo() -> dict[str, str]:
    with ARCHIVO.open(encoding="utf-8", newline="") as archivo:
        return {fila["ciiu"]: fila["descripcion"] for fila in csv.DictReader(archivo)}


def descripcion(ciiu: str) -> str | None:
    return catalogo().get((ciiu or "").strip())


def buscar(consulta: str, limite: int = 20) -> list[dict[str, str]]:
    """Clases cuyo código empieza por la consulta o cuyo título contiene todas sus palabras."""
    consulta = (consulta or "").strip()
    if not consulta:
        return []
    palabras = _plano(consulta).split()
    salida = []
    for codigo, titulo in catalogo().items():
        if codigo.startswith(consulta) or all(p in _plano(titulo) for p in palabras):
            salida.append({"ciiu": codigo, "descripcion": titulo})
            if len(salida) >= limite:
                break
    return salida
