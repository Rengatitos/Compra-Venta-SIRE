"""Lo que dice el plan de cuentas sobre una cuenta: su descripción y su jerarquía.

Una cuenta como 603202523 se entiende por su camino en el plan: 60 COMPRAS ›
603 MATERIALES AUXILIARES, SUMINISTROS Y REPUESTOS › 6032 SUMINISTROS ›
603202523 SUMINISTROS ENERGIA - Compras. Ese camino va en el motivo de cada
clasificación, para que el contador vea qué es la cuenta sin abrir el plan.

Se busca primero en el maestro de cuentas de la empresa (el que cargó en «Maestro
de cuentas») y, para lo que no esté ahí, en el plan CONTASIS del conocimiento
del clasificador.
"""

from __future__ import annotations

from functools import cache
from typing import Any

from app.repositories import plan_cuentas as repo_plan_cuentas
from app.services.clasificador.config import RECURSOS
from app.services.plan_cuentas_service import desde_excel

PLAN_CONTASIS = RECURSOS / "conocimiento" / "plan_cuentas" / "PLAN_DE_CUENTAS_CONTASIS.xlsx"


@cache
def plan_contasis() -> dict[str, str]:
    """Código → descripción del plan CONTASIS (se lee una vez por proceso)."""
    return {c.cuenta: c.descripcion for c in desde_excel(PLAN_CONTASIS.read_bytes())}


def _prefijos(codigo: str) -> list[str]:
    return [codigo[:n] for n in range(2, len(codigo) + 1)]


async def jerarquia(db, empresa_id: str, codigo: str | None) -> list[dict[str, Any]]:
    """Cuentas del camino de `codigo` que existen en el plan, de la más general a ella.

    Vacía si no hay código. Si el código no está en ningún plan, el último
    tramo sale sin descripción para que se note.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return []
    prefijos = _prefijos(codigo)
    de_la_empresa = (
        await repo_plan_cuentas.descripciones(db, empresa_id, prefijos) if db is not None else {}
    )
    generico = plan_contasis()
    camino = [
        {"codigo": p, "descripcion": de_la_empresa.get(p) or generico.get(p)}
        for p in prefijos
        if p in de_la_empresa or p in generico
    ]
    if not camino or camino[-1]["codigo"] != codigo:
        camino.append({"codigo": codigo, "descripcion": None})
    return camino


def texto_jerarquia(camino: list[dict[str, Any]]) -> str:
    return " › ".join(
        f"{c['codigo']} {c['descripcion']}" if c.get("descripcion") else c["codigo"]
        for c in camino
    )
