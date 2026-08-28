from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from bson.decimal128 import Decimal128

NOMBRE_COL_EMPRESAS = "empresas"
NOMBRE_COL_PERIODOS = "periodos"
NOMBRE_COL_COMPROBANTES = "comprobantes"
NOMBRE_COL_JOBS = "jobs"
NOMBRE_COL_VECTOR_GLOBAL = "vector_global"
NOMBRE_COL_VECTOR_USUARIOS = "vector_usuarios"


def monto_a_bson(valor: Decimal | None) -> Decimal128 | None:
    if valor is None:
        return None
    return Decimal128(valor)


def monto_desde_bson(valor: Any) -> Decimal:
    if isinstance(valor, Decimal128):
        return valor.to_decimal()
    if isinstance(valor, Decimal):
        return valor
    if valor is None:
        return Decimal("0.00")
    return Decimal(str(valor))


def monto_a_float(valor: Any) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, Decimal128):
        return float(valor.to_decimal())
    if isinstance(valor, Decimal):
        return float(valor)
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def fecha_a_bson(valor: date | None) -> datetime | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    return datetime(valor.year, valor.month, valor.day, tzinfo=UTC)


def fecha_desde_bson(valor: Any) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None
