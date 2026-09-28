"""Una solicitud de procesamiento masivo, sin depender de Mongo ni de la cola.

El contador elige empresas y periodos. Cada pareja (RUC, periodo) es un
*item*, y cada item recorre sus pasos en orden:

    credenciales (si faltan) → SIRE compras → SIRE ventas
      → comprobantes de compras → comprobantes de ventas
      → clasificación de compras → clasificación de ventas

Cada paso es un trabajo de la cola durable. Cuando todos los items terminan,
se arma el ZIP y se envían los correos. Aquí vive el orden, qué hace fallar a
un item y cómo se llaman las carpetas; quién encola qué lo decide
`app.services.solicitudes_service`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from enum import Enum
from typing import Any

from app.domain.comprobante import Libro
from app.domain.jobs import TipoJob

# Perú no tiene horario de verano: un desplazamiento fijo basta y no depende de
# que el sistema traiga la base de zonas horarias (en Windows no la trae).
ZONA_PERU = timezone(timedelta(hours=-5), "America/Lima")


class EstadoSolicitud(str, Enum):
    EN_PROGRESO = "en_progreso"
    # Todos los items terminaron: se arman los archivos y el ZIP.
    EMPAQUETANDO = "empaquetando"
    ENVIANDO = "enviando"
    COMPLETADA = "completada"
    COMPLETADA_CON_ERRORES = "completada_con_errores"
    FALLIDA = "fallida"


ESTADOS_SOLICITUD_TERMINALES = frozenset({
    EstadoSolicitud.COMPLETADA,
    EstadoSolicitud.COMPLETADA_CON_ERRORES,
    EstadoSolicitud.FALLIDA,
})


class EstadoItem(str, Enum):
    PENDIENTE = "pendiente"
    EN_PROGRESO = "en_progreso"
    COMPLETADO = "completado"
    # Terminó, pero algún paso posterior a la descarga SIRE falló.
    CON_ERRORES = "con_errores"
    # Sin descarga SIRE no hay nada que procesar: el resto de pasos se omite.
    FALLIDO = "fallido"


ESTADOS_ITEM_TERMINALES = frozenset(
    {EstadoItem.COMPLETADO, EstadoItem.CON_ERRORES, EstadoItem.FALLIDO}
)


class EstadoPaso(str, Enum):
    PENDIENTE = "pendiente"
    # Tiene job en la cola (pendiente, en curso o esperando reintento).
    ENCOLADO = "encolado"
    COMPLETADO = "completado"
    FALLIDO = "fallido"
    OMITIDO = "omitido"


ESTADOS_PASO_TERMINALES = frozenset(
    {EstadoPaso.COMPLETADO, EstadoPaso.FALLIDO, EstadoPaso.OMITIDO}
)


class Paso(str, Enum):
    CREDENCIALES = "credenciales"
    SIRE_COMPRAS = "sire_compras"
    SIRE_VENTAS = "sire_ventas"
    DETALLE_COMPRAS = "detalle_compras"
    DETALLE_VENTAS = "detalle_ventas"
    CLASIFICACION_COMPRAS = "clasificacion_compras"
    CLASIFICACION_VENTAS = "clasificacion_ventas"


# Qué trabajo de la cola ejecuta cada paso y sobre qué libro.
TRABAJO_DE_PASO: dict[Paso, tuple[TipoJob, Libro | None]] = {
    Paso.CREDENCIALES: (TipoJob.CREDENCIALES_SUNAT, None),
    Paso.SIRE_COMPRAS: (TipoJob.SINCRONIZACION_SIRE, Libro.COMPRAS),
    Paso.SIRE_VENTAS: (TipoJob.SINCRONIZACION_SIRE, Libro.VENTAS),
    Paso.DETALLE_COMPRAS: (TipoJob.EXTRACCION_DETALLES, Libro.COMPRAS),
    Paso.DETALLE_VENTAS: (TipoJob.EXTRACCION_DETALLES, Libro.VENTAS),
    Paso.CLASIFICACION_COMPRAS: (TipoJob.CLASIFICACION_CUENTAS, Libro.COMPRAS),
    Paso.CLASIFICACION_VENTAS: (TipoJob.CLASIFICACION_CUENTAS, Libro.VENTAS),
}

PASOS_SIRE = frozenset({Paso.SIRE_COMPRAS, Paso.SIRE_VENTAS})
PASOS_CLASIFICACION = frozenset({Paso.CLASIFICACION_COMPRAS, Paso.CLASIFICACION_VENTAS})


class EstadoEnvio(str, Enum):
    PENDIENTE = "pendiente"
    ENVIADO = "enviado"
    FALLIDO = "fallido"
    # Fuera de la lista blanca del entorno: no se envía.
    BLOQUEADO = "bloqueado"


class ModoEnvio(str, Enum):
    ADJUNTO = "adjunto"
    ENLACE = "enlace"


def pasos_del_item(
    *, necesita_credenciales: bool, clasificar: bool, motivo_sin_clasificar: str | None
) -> list[dict[str, Any]]:
    """Los pasos de un item, listos para guardar."""
    pasos: list[dict[str, Any]] = []
    for paso in Paso:
        estado = EstadoPaso.PENDIENTE
        nota = None
        if paso is Paso.CREDENCIALES and not necesita_credenciales:
            continue
        if paso in PASOS_CLASIFICACION and not clasificar:
            estado = EstadoPaso.OMITIDO
            nota = motivo_sin_clasificar or "No se pidió clasificar con IA"
        pasos.append({"paso": paso.value, "estado": estado.value, "job_id": None, "nota": nota})
    return pasos


def siguiente_paso(pasos: list[dict[str, Any]]) -> int | None:
    """Índice del primer paso pendiente, o None si ya no queda ninguno."""
    for i, paso in enumerate(pasos):
        if paso["estado"] == EstadoPaso.PENDIENTE.value:
            return i
    return None


def omitir_restantes(pasos: list[dict[str, Any]], motivo: str) -> None:
    for paso in pasos:
        if paso["estado"] == EstadoPaso.PENDIENTE.value:
            paso["estado"] = EstadoPaso.OMITIDO.value
            paso["nota"] = motivo


def estado_final_item(pasos: list[dict[str, Any]]) -> EstadoItem:
    """Estado de un item que ya no tiene pasos por correr."""
    fallidos = {Paso(p["paso"]) for p in pasos if p["estado"] == EstadoPaso.FALLIDO.value}
    if fallidos & PASOS_SIRE:
        return EstadoItem.FALLIDO
    if fallidos:
        return EstadoItem.CON_ERRORES
    return EstadoItem.COMPLETADO


def estado_final_solicitud(
    estados_items: list[EstadoItem], estados_envios: list[EstadoEnvio]
) -> EstadoSolicitud:
    if estados_items and all(e is EstadoItem.FALLIDO for e in estados_items):
        return EstadoSolicitud.FALLIDA
    limpio = all(e is EstadoItem.COMPLETADO for e in estados_items) and all(
        e in (EstadoEnvio.ENVIADO, EstadoEnvio.BLOQUEADO) for e in estados_envios
    )
    return EstadoSolicitud.COMPLETADA if limpio else EstadoSolicitud.COMPLETADA_CON_ERRORES


def fecha_peru(momento: datetime | None) -> date:
    """El día en Lima de un instante UTC; sin instante, hoy."""
    momento = momento or datetime.now(ZONA_PERU)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(ZONA_PERU).date()


def nombre_carpeta(ruc: str, periodo: str, ultima_actualizacion: datetime | None) -> str:
    """`RUC_AAAA-MM_AAAA-MM-DD`: periodo procesado y día de la última descarga SIRE."""
    return f"{ruc}_{periodo[:4]}-{periodo[4:6]}_{fecha_peru(ultima_actualizacion).isoformat()}"


def nombre_zip(creada: datetime | None) -> str:
    return f"DESCARGA_{fecha_peru(creada).isoformat()}.zip"
