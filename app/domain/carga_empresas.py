"""Qué es una fila válida en el alta de empresas, sin depender de Excel ni Mongo.

La carga masiva lee cuatro columnas (razón social, RUC, usuario y contraseña
SOL) y la individual es una carga de una sola fila: las dos pasan por
`validar_filas`, así un RUC se rechaza con el mismo motivo venga de donde venga.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

PREFIJOS_RUC = frozenset({"10", "15", "17", "20"})
PESOS_RUC = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
MAX_FILAS = 200


class Modalidad(str, Enum):
    INDIVIDUAL = "individual"
    MASIVA = "masiva"


class EstadoFila(str, Enum):
    # La empresa ya existe y la cola está completando sus datos de SUNAT.
    PENDIENTE = "pendiente"
    AGREGADA = "agregada"
    CON_OBSERVACIONES = "agregada_con_observaciones"
    # Existe, pero sin las credenciales del API SUNAT no sirve: hay que corregir
    # su RUC, usuario o clave SOL desde el panel de empresas y reintentar.
    REQUIERE_CORRECCION = "requiere_correccion"
    NO_AGREGADA = "no_agregada"


ESTADOS_FILA_TERMINALES = frozenset(
    {
        EstadoFila.AGREGADA,
        EstadoFila.CON_OBSERVACIONES,
        EstadoFila.REQUIERE_CORRECCION,
        EstadoFila.NO_AGREGADA,
    }
)


class EstadoCarga(str, Enum):
    EN_PROGRESO = "en_progreso"
    COMPLETADA = "completada"


class Motivo(str, Enum):
    REGISTRO_EXITOSO = "Registro exitoso"
    EN_PROCESO = "Completando los datos de SUNAT"
    RUC_EXISTENTE = "RUC ya registrado"
    RUC_INVALIDO = "RUC inválido"
    FALTA_RAZON_SOCIAL = "Falta razón social"
    FALTA_RUC = "Falta RUC"
    FALTA_USUARIO = "Falta usuario"
    FALTA_CONTRASENA = "Falta contraseña"
    DUPLICADO_EN_ARCHIVO = "Registro duplicado dentro del Excel"
    ERROR_CIIU = "Error al obtener el CIIU"
    ERROR_SUNAT = "Error al obtener información de SUNAT"
    OTRO = "Otro error"


@dataclass(frozen=True)
class FilaCarga:
    fila: int
    razon_social: str
    ruc: str
    usuario: str
    password: str = field(repr=False)


@dataclass
class ResultadoFila:
    fila: int
    ruc: str
    razon_social: str
    usuario: str
    estado: EstadoFila
    motivos: list[str]
    empresa_id: str | None = None
    fecha_registro: datetime | None = None

    def a_documento(self) -> dict[str, Any]:
        # Nunca la contraseña: la carga es un registro de trazabilidad que se
        # lista y se descarga como reporte.
        return {
            "fila": self.fila,
            "ruc": self.ruc,
            "razon_social": self.razon_social,
            "usuario": self.usuario,
            "estado": self.estado.value,
            "motivos": list(self.motivos),
            "empresa_id": self.empresa_id,
            "fecha_registro": self.fecha_registro,
        }


def es_ruc_valido(ruc: str) -> bool:
    """11 dígitos, prefijo de contribuyente y dígito verificador módulo 11."""
    ruc = (ruc or "").strip()
    if len(ruc) != 11 or not ruc.isdigit() or ruc[:2] not in PREFIJOS_RUC:
        return False
    suma = sum(int(digito) * peso for digito, peso in zip(ruc[:10], PESOS_RUC, strict=True))
    verificador = 11 - suma % 11
    verificador = {10: 0, 11: 1}.get(verificador, verificador)
    return verificador == int(ruc[10])


def validar_fila(
    fila: FilaCarga, *, exigir_razon_social: bool = True
) -> list[Motivo]:
    motivos: list[Motivo] = []
    if exigir_razon_social and not fila.razon_social:
        motivos.append(Motivo.FALTA_RAZON_SOCIAL)
    if not fila.ruc:
        motivos.append(Motivo.FALTA_RUC)
    elif not es_ruc_valido(fila.ruc):
        motivos.append(Motivo.RUC_INVALIDO)
    if not fila.usuario:
        motivos.append(Motivo.FALTA_USUARIO)
    if not fila.password:
        motivos.append(Motivo.FALTA_CONTRASENA)
    return motivos


def validar_filas(
    filas: list[FilaCarga],
    rucs_existentes: set[str],
    *,
    exigir_razon_social: bool = True,
) -> list[tuple[FilaCarga, list[Motivo]]]:
    """Cada fila con sus motivos de rechazo; sin motivos, la fila es válida.

    Un RUC repetido en el archivo vale en su primera fila válida y se rechaza
    en las demás; uno que ya está en la base se rechaza siempre. Una fila
    incompleta no «gasta» el RUC: si más abajo viene completa, esa es la que
    se registra.
    """
    vistos: set[str] = set()
    resultado: list[tuple[FilaCarga, list[Motivo]]] = []
    for fila in filas:
        motivos = validar_fila(fila, exigir_razon_social=exigir_razon_social)
        if fila.ruc and Motivo.RUC_INVALIDO not in motivos:
            if fila.ruc in rucs_existentes:
                motivos.append(Motivo.RUC_EXISTENTE)
            elif fila.ruc in vistos:
                motivos.append(Motivo.DUPLICADO_EN_ARCHIVO)
        if not motivos:
            vistos.add(fila.ruc)
        resultado.append((fila, motivos))
    return resultado
