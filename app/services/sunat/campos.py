"""Utilidades compartidas por los mapeos del RCE y del RVIE.

Viven en su propio módulo y no en `propuesta.py` porque los dos mapeos las
necesitan y `propuesta.py` importa a ambos para despachar por libro: dejarlas
allí montaba un ciclo de imports.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

# Bloques que el SIRE manda anidados y cuyos campos los mapeos buscan por su
# nombre suelto. `tipoCambio` es fácil de pasar por alto: el tipo de cambio no
# vive en la raíz del registro sino dentro de él, así que sin aplanarlo la
# columna se quedaba vacía incluso en los comprobantes en dólares.
_BLOQUES_ANIDADOS = ("montos", "tipoCambio")


def fuente(registro: dict[str, Any]) -> dict[str, Any]:
    """Aplana los bloques anidados del SIRE sobre la raíz del registro.

    El SIRE a veces manda los importes anidados y a veces sueltos en la raíz,
    así que los mapeos buscan en una única vista de los dos.
    """
    plano = dict(registro)
    for bloque in _BLOQUES_ANIDADOS:
        anidados = registro.get(bloque)
        if isinstance(anidados, dict):
            plano.update(anidados)
    return plano


def primero(datos: dict[str, Any], campos: tuple[str, ...], defecto: Any = "") -> Any:
    for campo in campos:
        valor = datos.get(campo)
        if valor not in (None, "", "0"):
            return valor
    return defecto


def sumar(datos: dict[str, Any], campos: tuple[str, ...]) -> Decimal:
    total = Decimal("0")
    for campo in campos:
        valor = datos.get(campo)
        if valor in (None, ""):
            continue
        try:
            total += Decimal(str(valor))
        except (InvalidOperation, ValueError):
            continue
    return total


def monto(datos: dict[str, Any], campos: tuple[str, ...]) -> Decimal:
    """Importe del primer campo que traiga valor, como `Decimal`.

    Se usa cuando la tupla son alias del *mismo* concepto: sumarlos con
    `sumar` duplicaría el importe si SUNAT mandara dos de ellos a la vez.
    """
    valor = primero(datos, campos, 0)
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def tasa_porcentual(datos: dict[str, Any], campos: tuple[str, ...]) -> Decimal | None:
    """Tasa de IGV en puntos porcentuales, o `None` si el comprobante no trae.

    Se devuelve `None` en vez de la tasa general para no falsear los
    comprobantes no gravados ni los del régimen de selva (10.5 %).

    SUNAT manda la tasa como fracción (`0.18`, `0.105`) y el registro la pide
    en puntos, de ahí el x100. Pero eso no está confirmado para el RVIE, y
    multiplicar a ciegas un `18` que ya viniera en puntos escribiría `1800` en
    la columna de tasa del Excel, así que se convierte sólo lo que de verdad
    parece una fracción.
    """
    valor = primero(datos, campos, None)
    if valor is None:
        return None
    try:
        tasa = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    if tasa <= 0:
        return None
    return tasa * 100 if tasa < 1 else tasa


# El periodo al que SUNAT asigna el comprobante. No es el mes de emisión: una
# factura de julio anotada en agosto llega en la propuesta de agosto con
# `perTributario=202608`, que es donde le toca estar en el registro. El RCE lo
# llama `perTributario` y el RVIE `perPeriodoTributario`.
CAMPOS_PERIODO = ("perTributario", "perPeriodoTributario")


def periodo_tributario(registro: dict[str, Any]) -> str:
    valor = primero(registro, CAMPOS_PERIODO, "")
    return str(valor).strip()
