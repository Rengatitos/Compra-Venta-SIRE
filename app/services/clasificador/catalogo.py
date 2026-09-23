"""Búsqueda directa de cuentas imputables en el plan CONTASIS.

La búsqueda semántica del RAG encuentra la familia de la cuenta, pero no
siempre la divisionaria: «ADQUISICION DE COMBUSTIBLE» a veces traía
603202521 SUMINISTROS COMBUSTIBLES y a veces no, según cómo redactara la IA la
interpretación. Esto la complementa con una coincidencia léxica sobre las
cuentas del plan, con raíces para que «combustible» y «COMBUSTIBLES» casen.

Solo devuelve **hojas** (divisionarias sin subcuentas): son las únicas en las
que Contasis deja registrar un asiento.
"""

from __future__ import annotations

import re
import unicodedata
from functools import cache

from app.services.plan_contable import plan_contasis

# Palabras que describen el tipo de operación, no el bien o servicio: casan
# con medio plan («Compras», «Servicios») y no distinguen nada.
_GENERICAS = frozenset(
    """compra compras venta ventas adquisicion adquisiciones bien bienes servicio servicios
    costo costos gasto gastos operacion operaciones pago pagos insumo insumos local
    emision emitida emitidas empresa terceros tercero otro otros otras para como
    por con del los las una unos sus este esta""".split()
)
_PALABRA = re.compile(r"[a-z0-9]+")


def raiz(palabra: str) -> str:
    """Raíz tosca que iguala singular y plural.

    combustible/combustibles → combustibl, material/materiales → material,
    suministro/suministros → suministro. Quitar la «s» y luego la «e» final
    cubre los dos plurales del castellano (-s y -es).
    """
    if len(palabra) > 4 and palabra.endswith("s"):
        palabra = palabra[:-1]
    if len(palabra) > 5 and palabra.endswith("e"):
        palabra = palabra[:-1]
    return palabra


def raices(texto: str) -> set[str]:
    plano = unicodedata.normalize("NFKD", (texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return {
        raiz(p) for p in _PALABRA.findall(plano)
        if len(p) > 3 and not p.isdigit() and p not in _GENERICAS
    }


@cache
def hojas() -> dict[str, tuple[str, frozenset[str]]]:
    """Cuentas imputables del plan: código → (descripción, sus raíces)."""
    plan = plan_contasis()
    codigos = sorted(plan)
    salida = {}
    for i, codigo in enumerate(codigos):
        siguiente = codigos[i + 1] if i + 1 < len(codigos) else ""
        if not siguiente.startswith(codigo):  # sin subcuentas
            salida[codigo] = (plan[codigo], frozenset(raices(plan[codigo])))
    return salida


def es_hoja(codigo: str) -> bool:
    return codigo in hojas()


def buscar(texto: str, prefijos: tuple[str, ...], limite: int = 8) -> list[tuple[str, str, float]]:
    """Hojas cuyos prefijos se permiten y cuya descripción comparte raíces con `texto`.

    El puntaje es la fracción de las raíces de la descripción que aparecen en
    el texto: premia la cuenta cuyo nombre está entero en lo que se compra.
    """
    buscadas = raices(texto)
    if not buscadas:
        return []
    encontradas = []
    for codigo, (descripcion, suyas) in hojas().items():
        if not codigo.startswith(prefijos) or not suyas:
            continue
        comunes = buscadas & suyas
        if comunes:
            encontradas.append((codigo, descripcion, len(comunes) / len(suyas)))
    encontradas.sort(key=lambda e: (-e[2], len(e[0]), e[0]))
    return encontradas[:limite]
