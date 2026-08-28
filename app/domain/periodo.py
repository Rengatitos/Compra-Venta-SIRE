from __future__ import annotations

import re

PERIODO_RE = re.compile(r"^20\d{2}(0[1-9]|1[0-2])$")

MENSAJE_FORMATO = "El periodo debe tener el formato YYYYMM (por ejemplo 202606)"


def es_valido(periodo: str) -> bool:
    return bool(PERIODO_RE.match(periodo or ""))


def validar(periodo: str) -> str:
    if not es_valido(periodo):
        raise ValueError(MENSAJE_FORMATO)
    return periodo


def anio_mes(periodo: str) -> tuple[int, int]:
    validar(periodo)
    return int(periodo[:4]), int(periodo[4:])
