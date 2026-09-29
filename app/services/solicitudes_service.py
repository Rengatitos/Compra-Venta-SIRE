"""Orquestador de las solicitudes de procesamiento masivo.

`crear` arma los items (RUC × periodo) y encola el primer paso de cada uno. A
partir de ahí manda la cola: cada vez que un paso queda cerrado (completado, o
fallido sin más reintentos) el worker llama a `al_terminar`, que encola el
paso siguiente de ese item. Cuando todos los items terminan se encola el
empaquetado y, tras él, el envío de correos. Nada depende de que el contador
siga conectado.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.domain import periodo as dominio_periodo
from app.domain.jobs import EstadoJob, Job, TipoJob
from app.domain.solicitudes import (
    ESTADOS_ITEM_TERMINALES,
    PASOS_SIRE,
    TRABAJO_DE_PASO,
    ZONA_PERU,
    EstadoEnvio,
    EstadoItem,
    EstadoPaso,
    EstadoSolicitud,
    Paso,
    estado_final_item,
    estado_final_solicitud,
    nombre_zip,
    omitir_restantes,
    pasos_del_item,
    siguiente_paso,
)
from app.repositories import empresas as repo_empresas
from app.repositories import jobs as repo_jobs
from app.repositories import periodos as repo_periodos
from app.repositories import solicitudes as repo_solicitudes
from app.services import cola, integracion_externos, jobs_service
from app.services.cola.errores import ErrorPermanente

logger = logging.getLogger(__name__)

MAX_ITEMS = 500
TODAS = "todas"
TODOS = "todos"
OMITIDO_POR_SIRE = "Sin la descarga SIRE no se puede continuar con este periodo"


class SolicitudInvalida(ValueError):
    """La selección no se puede procesar: la corrige el usuario."""


def _periodo_actual() -> str:
    return datetime.now(ZONA_PERU).strftime("%Y%m")


def carril(paso: Paso, ruc: str) -> str | None:
    tipo, _ = TRABAJO_DE_PASO[paso]
    if tipo is TipoJob.CLASIFICACION_CUENTAS:
        return cola.CARRIL_CLASIFICADOR
    if tipo is TipoJob.SINCRONIZACION_SIRE:
        # El API SIRE no usa la sesión SOL: no espera a los scrapings, pero sí
        # a las otras descargas de la misma empresa (comparten el token).
        return f"sire:{ruc}"
    return cola.carril_sol(ruc)


# --- Crear -------------------------------------------------------------------


async def _empresas(db, rucs: list[str] | str) -> list[dict[str, Any]]:
    if rucs == TODAS:
        return await repo_empresas.listar(db, limit=MAX_ITEMS)
    if not rucs:
        raise SolicitudInvalida("Elige al menos una empresa")
    empresas = []
    for ruc in dict.fromkeys(rucs):
        empresa = await repo_empresas.obtener_por_ruc(db, ruc)
        if not empresa:
            raise SolicitudInvalida(f"No hay ninguna empresa con el RUC {ruc}")
        empresas.append(empresa)
    return empresas


async def _periodos(db, empresa: dict[str, Any], periodos: list[str] | str) -> list[str]:
    empresa_id = str(empresa["_id"])
    if periodos == TODOS:
        return sorted(p["periodo"] for p in await repo_periodos.listar(db, empresa_id, limit=240))
    elegidos = []
    for periodo in dict.fromkeys(periodos):
        if not dominio_periodo.es_valido(periodo):
            raise SolicitudInvalida(f"Periodo inválido: {periodo} (formato AAAAMM)")
        if periodo > _periodo_actual():
            raise SolicitudInvalida(f"El periodo {periodo} todavía no ha empezado")
        if not await repo_periodos.obtener(db, empresa_id, periodo):
            try:
                await repo_periodos.crear(db, empresa_id, periodo)
            except DuplicateKeyError:
                pass
            await integracion_externos.refrescar(db, empresa_id, periodo)
        elegidos.append(periodo)
    return sorted(elegidos)


async def crear(
    db,
    *,
    creado_por: str,
    empresas: list[str] | str,
    periodos: list[str] | str,
    clasificar: bool = True,
) -> dict[str, Any]:
    if periodos != TODOS and not periodos:
        raise SolicitudInvalida("Elige al menos un periodo")
    motivo_sin_clasificar = None
    if clasificar and not settings.CLASIFICADOR_HABILITADO:
        motivo_sin_clasificar = "El clasificador contable está deshabilitado en este servidor"

    items = []
    for empresa in await _empresas(db, empresas):
        tiene_credenciales = empresa.get("sunat_client_id") and empresa.get("sunat_client_secret")
        for periodo in await _periodos(db, empresa, periodos):
            items.append({
                "ruc": empresa["ruc"],
                "nombre": empresa.get("nombre"),
                "periodo": periodo,
                "estado": EstadoItem.PENDIENTE.value,
                "observaciones": [],
                "pasos": pasos_del_item(
                    necesita_credenciales=not tiene_credenciales,
                    clasificar=clasificar and settings.CLASIFICADOR_HABILITADO,
                    motivo_sin_clasificar=motivo_sin_clasificar,
                ),
            })
    if not items:
        raise SolicitudInvalida(
            "Las empresas elegidas no tienen periodos registrados; elige periodos concretos"
        )
    if len(items) > MAX_ITEMS:
        raise SolicitudInvalida(f"Como máximo {MAX_ITEMS} empresas × periodos por solicitud")

    ahora = datetime.now(UTC)
    solicitud_id = await repo_solicitudes.crear(db, {
        "creado_por": creado_por,
        "creado_en": ahora,
        "actualizado_en": ahora,
        "terminado_en": None,
        "estado": EstadoSolicitud.EN_PROGRESO.value,
        "clasificar": clasificar,
        "items": items,
        "zip": None,
        "envios": [],
        "error": None,
    })
    # Con el candado tomado: si un primer paso terminara antes de guardarse su
    # `job_id` en el item, `al_terminar` no lo encontraría y el item quedaría
    # encolado para siempre. Así espera a que el item esté guardado.
    async with jobs_service.candado(f"solicitud:{solicitud_id}"):
        for indice, item in enumerate(items):
            await _avanzar(db, solicitud_id, indice, item)
    logger.info(
        "Solicitud %s de %s: %s items", solicitud_id, creado_por, len(items)
    )
    return await repo_solicitudes.obtener(db, solicitud_id)


# --- Avance ------------------------------------------------------------------


async def _encolar_paso(
    db, solicitud_id: str, indice: int, item: dict[str, Any], paso: Paso
) -> Job:
    tipo, libro = TRABAJO_DE_PASO[paso]
    parametros: dict[str, Any] = {"indice_item": indice, "paso": paso.value}
    if tipo is TipoJob.EXTRACCION_DETALLES:
        parametros["hasta_terminar"] = True
    if tipo is TipoJob.CLASIFICACION_CUENTAS:
        parametros["automatica"] = True
    return await cola.encolar(
        db,
        tipo,
        item["ruc"],
        item["periodo"],
        libro,
        cola=carril(paso, item["ruc"]),
        parametros=parametros,
        solicitud_id=solicitud_id,
    )


async def _avanzar(db, solicitud_id: str, indice: int, item: dict[str, Any]) -> None:
    """Encola el siguiente paso del item o, si no queda ninguno, lo cierra."""
    siguiente = siguiente_paso(item["pasos"])
    if siguiente is None:
        item["estado"] = estado_final_item(item["pasos"]).value
    else:
        paso = item["pasos"][siguiente]
        job = await _encolar_paso(db, solicitud_id, indice, item, Paso(paso["paso"]))
        paso["estado"] = EstadoPaso.ENCOLADO.value
        paso["job_id"] = job.job_id
        item["estado"] = EstadoItem.EN_PROGRESO.value
    await repo_solicitudes.guardar_item(db, solicitud_id, indice, item)


def _nota(job: Job) -> str | None:
    resultado = job.resultado or {}
    if job.tipo is TipoJob.SINCRONIZACION_SIRE and resultado.get("sin_propuesta"):
        return "SUNAT no tiene propuesta para este libro"
    if job.tipo is TipoJob.CLASIFICACION_CUENTAS and resultado.get("errores_persistentes"):
        return f"{resultado['errores_persistentes']} comprobantes sin código tras varios intentos"
    return resultado.get("mensaje")


async def al_terminar(db, job: Job) -> None:
    """El worker avisa de que un trabajo de una solicitud quedó cerrado."""
    if not job.solicitud_id:
        return
    # Dos pasos de la misma solicitud pueden cerrar a la vez: el candado evita
    # que uno pise el item que acaba de guardar el otro.
    async with jobs_service.candado(f"solicitud:{job.solicitud_id}"):
        solicitud = await repo_solicitudes.obtener(db, job.solicitud_id)
        if not solicitud:
            return
        if job.tipo is TipoJob.EMPAQUETADO:
            await _tras_empaquetar(db, solicitud, job)
        elif job.tipo is TipoJob.ENVIO_CORREO:
            await _tras_enviar(db, solicitud, job)
        else:
            await _tras_paso(db, solicitud, job)


async def _tras_paso(db, solicitud: dict[str, Any], job: Job) -> None:
    solicitud_id = str(solicitud["_id"])
    indice = job.parametros.get("indice_item")
    if indice is None or indice >= len(solicitud["items"]):
        return
    item = solicitud["items"][indice]
    paso = next((p for p in item["pasos"] if p.get("job_id") == job.job_id), None)
    if paso is None or paso["estado"] != EstadoPaso.ENCOLADO.value:
        # Un aviso repetido o de un paso que ya se reintentó con otro job.
        return

    if job.estado is EstadoJob.COMPLETADO:
        paso["estado"] = EstadoPaso.COMPLETADO.value
        paso["nota"] = _nota(job)
    else:
        paso["estado"] = EstadoPaso.FALLIDO.value
        paso["nota"] = job.error
        item["observaciones"].append(f"{paso['paso']}: {job.error}")
        if Paso(paso["paso"]) in PASOS_SIRE:
            omitir_restantes(item["pasos"], OMITIDO_POR_SIRE)
            for pendiente in item["pasos"]:
                if pendiente.get("nota") == OMITIDO_POR_SIRE:
                    pendiente["por_sire"] = True

    await _avanzar(db, solicitud_id, indice, item)
    if all(EstadoItem(i["estado"]) in ESTADOS_ITEM_TERMINALES for i in solicitud["items"]):
        await _empaquetar(db, solicitud_id)


async def _empaquetar(db, solicitud_id: str) -> None:
    if not await repo_solicitudes.reservar_empaquetado(db, solicitud_id):
        return
    await cola.encolar(
        db, TipoJob.EMPAQUETADO, "", "", cola=None, solicitud_id=solicitud_id, max_intentos=3,
    )


async def _tras_empaquetar(db, solicitud: dict[str, Any], job: Job) -> None:
    solicitud_id = str(solicitud["_id"])
    if job.estado is not EstadoJob.COMPLETADO:
        await repo_solicitudes.actualizar(db, solicitud_id, {
            "estado": EstadoSolicitud.FALLIDA.value,
            "error": f"No se pudieron generar los archivos: {job.error}",
            "terminado_en": datetime.now(UTC),
        })
        return
    await repo_solicitudes.actualizar(db, solicitud_id, {
        "estado": EstadoSolicitud.ENVIANDO.value, "zip": job.resultado,
    })
    await cola.encolar(
        db, TipoJob.ENVIO_CORREO, "", "", cola="correo", solicitud_id=solicitud_id,
    )


async def _tras_enviar(db, solicitud: dict[str, Any], job: Job) -> None:
    estados_items = [EstadoItem(i["estado"]) for i in solicitud["items"]]
    estados_envios = [EstadoEnvio(e["estado"]) for e in solicitud.get("envios") or []]
    if job.estado is not EstadoJob.COMPLETADO and not estados_envios:
        estados_envios = [EstadoEnvio.FALLIDO]
    final = estado_final_solicitud(estados_items, estados_envios)
    await repo_solicitudes.actualizar(db, str(solicitud["_id"]), {
        "estado": final.value,
        "error": job.error if job.estado is not EstadoJob.COMPLETADO else None,
        "terminado_en": datetime.now(UTC),
    })
    logger.info("Solicitud %s terminada: %s", solicitud["_id"], final.value)


# --- Reintentar --------------------------------------------------------------


async def reintentar(db, solicitud_id: str) -> dict[str, Any]:
    """Vuelve a encolar lo que falló: pasos, empaquetado o correos."""
    async with jobs_service.candado(f"solicitud:{solicitud_id}"):
        solicitud = await repo_solicitudes.obtener(db, solicitud_id)
        if not solicitud:
            raise SolicitudInvalida("Solicitud no encontrada")
        estado = EstadoSolicitud(solicitud["estado"])

        tocados = []
        for indice, item in enumerate(solicitud["items"]):
            reabierto = False
            for paso in item["pasos"]:
                if paso["estado"] == EstadoPaso.FALLIDO.value or paso.get("por_sire"):
                    paso.update({"estado": EstadoPaso.PENDIENTE.value, "job_id": None,
                                 "nota": None, "por_sire": False})
                    reabierto = True
            if reabierto:
                item["observaciones"] = []
                tocados.append((indice, item))

        if tocados:
            await repo_solicitudes.actualizar(db, solicitud_id, {
                "estado": EstadoSolicitud.EN_PROGRESO.value,
                "zip": None, "envios": [], "error": None, "terminado_en": None,
            })
            for indice, item in tocados:
                await _avanzar(db, solicitud_id, indice, item)
        elif estado is EstadoSolicitud.FALLIDA and not solicitud.get("zip"):
            await repo_solicitudes.actualizar(db, solicitud_id, {
                "estado": EstadoSolicitud.EN_PROGRESO.value, "error": None, "terminado_en": None,
            })
            await _empaquetar(db, solicitud_id)
        elif any(
            e["estado"] == EstadoEnvio.FALLIDO.value for e in solicitud.get("envios") or []
        ):
            envios = [
                {**e, "estado": EstadoEnvio.PENDIENTE.value, "definitivo": False}
                if e["estado"] == EstadoEnvio.FALLIDO.value else e
                for e in solicitud["envios"]
            ]
            await repo_solicitudes.actualizar(db, solicitud_id, {
                "estado": EstadoSolicitud.ENVIANDO.value, "envios": envios, "terminado_en": None,
            })
            await cola.encolar(
                db, TipoJob.ENVIO_CORREO, "", "", cola="correo", solicitud_id=solicitud_id,
            )
        else:
            raise SolicitudInvalida("No hay nada fallido que reintentar")
    return await repo_solicitudes.obtener(db, solicitud_id)


# --- Manejadores de la cola --------------------------------------------------


async def empaquetar(db, job: Job, reportar) -> dict[str, Any]:
    """Manejador de `empaquetado`: el ZIP con todas las empresas y periodos."""
    from app.services import empaquetado_service

    solicitud = await repo_solicitudes.obtener(db, job.solicitud_id or "")
    if not solicitud:
        raise ErrorPermanente("La solicitud ya no existe")
    await reportar(0, 1, "Generando los Excel y organizando los comprobantes")
    destino = (
        empaquetado_service.raiz_solicitud(str(solicitud["_id"]))
        / nombre_zip(solicitud["creado_en"])
    )
    resultado = await empaquetado_service.armar_zip(db, solicitud["items"], destino)
    await reportar(1, 1, f"ZIP listo: {resultado['archivo']}")
    return resultado


# --- Lectura -----------------------------------------------------------------


def _paso_con_job(paso: dict[str, Any], jobs: dict[str, Job]) -> dict[str, Any]:
    job = jobs.get(paso.get("job_id") or "")
    salida = {
        "paso": paso["paso"],
        "estado": paso["estado"],
        "job_id": paso.get("job_id"),
        "nota": paso.get("nota"),
    }
    if job:
        salida.update({
            "job_estado": job.estado.value,
            "intentos": job.intentos,
            "max_intentos": job.max_intentos,
            "siguiente_intento_en": job.siguiente_intento_en,
            "mensaje": job.progreso.mensaje,
            "error": job.error,
        })
    return salida


async def detalle(db, solicitud: dict[str, Any], *, con_jobs: bool = True) -> dict[str, Any]:
    """La solicitud para la API, con el estado vivo de cada paso."""
    jobs: dict[str, Job] = {}
    if con_jobs:
        jobs = {j.job_id: j for j in await repo_jobs.listar_de_solicitud(db, str(solicitud["_id"]))}
    items = solicitud.get("items") or []
    terminados = sum(1 for i in items if EstadoItem(i["estado"]) in ESTADOS_ITEM_TERMINALES)
    zip_ = solicitud.get("zip") or None
    return {
        "id": str(solicitud["_id"]),
        "creado_por": solicitud["creado_por"],
        "creado_en": solicitud["creado_en"],
        "terminado_en": solicitud.get("terminado_en"),
        "estado": solicitud["estado"],
        "clasificar": solicitud.get("clasificar", True),
        "error": solicitud.get("error"),
        "progreso": {"actual": terminados, "total": len(items)},
        "items": [
            {
                "ruc": item["ruc"],
                "nombre": item.get("nombre"),
                "periodo": item["periodo"],
                "estado": item["estado"],
                "observaciones": item.get("observaciones") or [],
                "pasos": [_paso_con_job(p, jobs) for p in item["pasos"]],
            }
            for item in items
        ],
        "zip": (
            {"archivo": zip_["archivo"], "bytes": zip_["bytes"],
             "generado_en": zip_["generado_en"]}
            if zip_ else None
        ),
        "envios": [
            {k: e.get(k) for k in (
                "correo", "empresas", "periodos", "estado", "modo", "intentos", "error",
                "creado_en", "enviado_en",
            )}
            for e in solicitud.get("envios") or []
        ],
    }
