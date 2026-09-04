"""Maestro de cuentas contables (PCGE) de una empresa.

Lógica pura: entran filas de celdas, salen cuentas. No sabe de openpyxl ni de
Mongo, así que se puede probar contra el archivo real sin levantar nada.

La forma del Excel de Contasis tiene dos trampas que un lector ingenuo se come:

1. **El código no está en una columna, está en tres.** La jerarquía se dibuja
   con la sangría: el elemento va en la primera columna, la cuenta en la
   segunda y la subcuenta y sus divisionarias en la tercera. Una fila trae el
   código en una sola de las tres, y cuál es indica el nivel.
2. **La última fila no es una cuenta.** Contasis firma el archivo con
   "Generado automáticamente por GESTIÓN CONTABLE… el 26/06/2026" metido en la
   columna del código. Leído de corrido entra como una cuenta de 98 caracteres.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel

# Cabeceras que identifican la hoja. Se buscan por texto en vez de asumir
# posiciones: el archivo lo exporta Contasis y las columnas se han movido entre
# versiones.
CAB_CUENTA = "CUENTA"
CAB_DESCRIPCION = "DESCRIPCION"
CAB_TIPO = "TIPO"
CAB_ANALISIS = "ANALISIS"
CAB_CENTRO_COSTOS = "CENTRO DE COSTOS"

NOMBRE_HOJA = "PLAN DE CUENTAS"

# Un código de cuenta del PCGE son dígitos: dos para el elemento y hasta una
# decena para las divisionarias. El techo es lo que descarta la firma de
# Contasis sin tener que reconocer su texto.
MAX_LARGO_CUENTA = 12


class Cuenta(BaseModel):
    """Una fila del maestro, ya limpia."""

    cuenta: str
    descripcion: str = ""
    tipo: str = ""
    analisis: str = ""
    centro_costos: str = ""
    # 1 = elemento, 2 = cuenta, 3 = subcuenta y divisionarias. Sale de en qué
    # columna venía el código, que es lo único que dibuja la jerarquía.
    nivel: int = 1


def _texto(valor: Any) -> str:
    """Celda a texto limpio.

    Contasis rellena a ancho fijo con espacios (`'01        '`), así que sin
    recortar cada valor nada casa después: ni las búsquedas, ni el índice
    único, ni el cruce con la clasificación de la IA.
    """
    if valor is None:
        return ""
    return str(valor).strip()


def es_codigo(valor: Any) -> bool:
    """Si la celda parece un código de cuenta y no un rótulo ni una firma."""
    texto = _texto(valor)
    if not texto or len(texto) > MAX_LARGO_CUENTA:
        return False
    # Los espacios interiores delatan una frase. Los códigos no los tienen.
    return not any(c.isspace() for c in texto)


class Columnas(BaseModel):
    """Dónde está cada dato dentro de la fila."""

    codigo: tuple[int, ...]
    descripcion: int
    tipo: int | None = None
    analisis: int | None = None
    centro_costos: int | None = None


def localizar_columnas(fila: Sequence[Any]) -> Columnas | None:
    """Mapea la fila de cabeceras, o `None` si no lo es.

    Las columnas del código son las que van desde donde dice «CUENTA» hasta
    justo antes de «DESCRIPCION»: son las que la hoja usa para la sangría y no
    llevan cabecera propia.
    """
    titulos = {_texto(v).upper(): i for i, v in enumerate(fila) if _texto(v)}

    inicio = titulos.get(CAB_CUENTA)
    descripcion = titulos.get(CAB_DESCRIPCION)
    if inicio is None or descripcion is None or descripcion <= inicio:
        return None

    return Columnas(
        codigo=tuple(range(inicio, descripcion)),
        descripcion=descripcion,
        tipo=titulos.get(CAB_TIPO),
        analisis=titulos.get(CAB_ANALISIS),
        centro_costos=titulos.get(CAB_CENTRO_COSTOS),
    )


def _celda(fila: Sequence[Any], indice: int | None) -> str:
    if indice is None or indice >= len(fila):
        return ""
    return _texto(fila[indice])


def _cuenta_de(fila: Sequence[Any], columnas: Columnas) -> Cuenta | None:
    for nivel, indice in enumerate(columnas.codigo, start=1):
        if indice >= len(fila):
            continue
        valor = fila[indice]
        if not es_codigo(valor):
            continue
        return Cuenta(
            cuenta=_texto(valor),
            descripcion=_celda(fila, columnas.descripcion),
            tipo=_celda(fila, columnas.tipo),
            analisis=_celda(fila, columnas.analisis),
            centro_costos=_celda(fila, columnas.centro_costos),
            nivel=nivel,
        )
    return None


def parsear(filas: Iterable[Sequence[Any]]) -> list[Cuenta]:
    """Cuentas del maestro, en el orden del archivo y sin duplicados.

    Las filas sin código utilizable —la cabecera, los separadores en blanco y
    la firma de Contasis del final— se descartan en silencio: son ruido
    conocido del formato, no errores que el usuario pueda arreglar.

    Si el mismo código aparece dos veces gana la primera aparición, que es la
    que respeta el orden jerárquico del archivo.
    """
    columnas: Columnas | None = None
    cuentas: list[Cuenta] = []
    vistas: set[str] = set()

    for fila in filas:
        if columnas is None:
            columnas = localizar_columnas(fila)
            # La fila de cabeceras no es una cuenta, así que se consume aquí.
            continue

        cuenta = _cuenta_de(fila, columnas)
        if cuenta is None or cuenta.cuenta in vistas:
            continue
        vistas.add(cuenta.cuenta)
        cuentas.append(cuenta)

    if columnas is None:
        raise ValueError(
            f"No se encontró la fila de cabeceras: se esperaban «{CAB_CUENTA}» y "
            f"«{CAB_DESCRIPCION}» en la hoja «{NOMBRE_HOJA}»"
        )

    return cuentas
