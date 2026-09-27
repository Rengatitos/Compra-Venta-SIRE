"""Qué hace cada tipo de trabajo de la cola.

Un manejador recibe el job tal como está en Mongo y reconstruye desde ahí lo
que necesita: la empresa se vuelve a leer por RUC y el resto sale de
`job.parametros`. Nada vive en memoria entre que se encola y se ejecuta, y por
eso un trabajo sobrevive a un reinicio.

Devuelve el `resultado` del job. Para fallar sin reintento lanza
`ErrorPermanente`; cualquier otra excepción se reintenta.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.comprobante import Libro
from app.domain.jobs import Job, TipoJob
from app.repositories import empresas as repo_empresas
from app.services.cola.errores import ErrorPermanente

logger = logging.getLogger(__name__)

Reportador = Callable[[int, int, str], Awaitable[None]]
Manejador = Callable[[AsyncIOMotorDatabase, Job, Reportador], Awaitable[dict[str, Any]]]

# Rondas de extracción de un mismo job cuando se pide terminar el periodo: cada
# ronda cubre `SUNAT_MAX_COMPROBANTES`, así que diez son mil comprobantes.
MAX_RONDAS_DETALLE = 10


async def empresa_de(db: AsyncIOMotorDatabase, job: Job) -> dict[str, Any]:
    empresa = await repo_empresas.obtener_por_ruc(db, job.ruc)
    if not empresa:
        raise ErrorPermanente(f"La empresa {job.ruc} ya no existe")
    return empresa


def libro_de(job: Job) -> Libro:
    if job.libro is None:
        raise ErrorPermanente("El trabajo no indica el libro")
    return job.libro


async def extraccion_detalles(db, job: Job, reportar: Reportador) -> dict[str, Any]:
    from app.services import detalle_service

    empresa = await empresa_de(db, job)
    libro = libro_de(job)
    resultado = await detalle_service.extraer(db, empresa, job.periodo, libro, reportar)
    if not job.parametros.get("hasta_terminar"):
        return resultado

    # En una solicitud masiva nadie va a relanzar el trabajo a mano: se sigue
    # mientras queden pendientes y la ronda anterior haya avanzado algo.
    rondas = 1
    acumulado = dict(resultado)
    while (
        resultado.get("pendientes")
        and resultado.get("procesados")
        and rondas < MAX_RONDAS_DETALLE
    ):
        rondas += 1
        resultado = await detalle_service.extraer(db, empresa, job.periodo, libro, reportar)
        for clave, valor in resultado.items():
            if isinstance(valor, int) and clave != "pendientes":
                acumulado[clave] = acumulado.get(clave, 0) + valor
        acumulado["pendientes"] = resultado.get("pendientes", 0)
        acumulado["mensaje"] = resultado.get("mensaje", acumulado.get("mensaje"))
    acumulado["rondas"] = rondas
    return acumulado


async def descarga_pdfs(db, job: Job, reportar: Reportador) -> dict[str, Any]:
    from app.services import pdf_service, zip_sunat_service

    empresa = await empresa_de(db, job)
    if job.libro is None:
        # Sin libro es el «ZIP completo» de compras y ventas del periodo.
        return await zip_sunat_service.preparar(db, empresa, job.periodo, job.job_id, reportar)
    return await pdf_service.descargar(db, empresa, job.periodo, job.libro, reportar)


async def detracciones(db, job: Job, reportar: Reportador) -> dict[str, Any]:
    from app.services import detracciones_service

    empresa = await empresa_de(db, job)
    try:
        return await detracciones_service.consultar(db, empresa, job.periodo, reportar)
    except ValueError as exc:
        raise ErrorPermanente(str(exc)) from exc


async def clasificacion_cuentas(db, job: Job, reportar: Reportador) -> dict[str, Any]:
    from app.services import clasificacion_service

    empresa = await empresa_de(db, job)
    return await clasificacion_service.clasificar_periodo(
        db,
        empresa,
        job.periodo,
        libro_de(job),
        reportar,
        reclasificar=bool(job.parametros.get("reclasificar")),
    )


async def credenciales_sunat(db, job: Job, reportar: Reportador) -> dict[str, Any]:
    from app.services import credenciales_sunat_service

    empresa = await empresa_de(db, job)
    if empresa.get("sunat_client_id") and empresa.get("sunat_client_secret"):
        return {"origen": "ya_tenia", "mensaje": "La empresa ya tenía sus credenciales de API"}
    await reportar(0, 1, "Entrando a SOL por el client_id y la clave del API SUNAT")
    resultado = await credenciales_sunat_service.obtener(db, empresa)
    await reportar(1, 1, resultado.get("mensaje", ""))
    return resultado


async def alta_empresa(db, job: Job, reportar: Reportador) -> dict[str, Any]:
    from app.services import carga_empresas_service

    return await carga_empresas_service.alta_empresa(db, job, reportar)


_MANEJADORES: dict[TipoJob, Manejador] = {
    TipoJob.EXTRACCION_DETALLES: extraccion_detalles,
    TipoJob.DESCARGA_PDFS: descarga_pdfs,
    TipoJob.DETRACCIONES: detracciones,
    TipoJob.CLASIFICACION_CUENTAS: clasificacion_cuentas,
    TipoJob.CREDENCIALES_SUNAT: credenciales_sunat,
    TipoJob.ALTA_EMPRESA: alta_empresa,
}


def registrar(tipo: TipoJob, manejador: Manejador) -> None:
    _MANEJADORES[tipo] = manejador


def manejador(tipo: TipoJob) -> Manejador:
    try:
        return _MANEJADORES[tipo]
    except KeyError:
        raise ErrorPermanente(f"No hay manejador para los trabajos de tipo {tipo.value}") from None
