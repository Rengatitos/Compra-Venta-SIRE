"""Reglas de la empresa que no dependen de Mongo ni de la API."""

from __future__ import annotations

import re
from collections.abc import Iterable

# Una comprobación de forma, no de existencia: `email-validator` no está entre
# las dependencias y para decidir a quién escribir basta con descartar lo que
# claramente no es una dirección. El frontend usa la misma expresión.
CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_CORREOS = 10


def es_correo_valido(correo: str) -> bool:
    return bool(CORREO_RE.match(correo or ""))


def normalizar_correos(correos: Iterable[str]) -> list[str]:
    """Recorta, pasa a minúsculas y quita duplicados conservando el orden.

    Lanza `ValueError` si alguno no tiene forma de correo o si son demasiados.
    """
    limpios: list[str] = []
    for correo in correos:
        correo = (correo or "").strip().lower()
        if not correo:
            continue
        if not es_correo_valido(correo):
            raise ValueError(f"«{correo}» no es un correo válido")
        if correo not in limpios:
            limpios.append(correo)
    if len(limpios) > MAX_CORREOS:
        raise ValueError(f"Como máximo {MAX_CORREOS} correos por empresa")
    return limpios
