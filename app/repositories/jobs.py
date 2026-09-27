from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.domain.comprobante import Libro
from app.domain.jobs import EstadoJob, Job, Progreso, TipoJob
from app.repositories._mongo import NOMBRE_COL_JOBS


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_JOBS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index("job_id", unique=True)
    await _col(db).create_index([("ruc", 1), ("periodo", 1)])
    # El historial se lee siempre por empresa y de lo mas reciente a lo mas
    # antiguo: sin este indice el sort se resuelve en memoria.
    await _col(db).create_index([("ruc", 1), ("creado_en", -1)])
    # Lo que consulta el worker en cada vuelta, y los pasos de una solicitud.
    await _col(db).create_index([("gestionado", 1), ("estado", 1), ("creado_en", 1)])
    await _col(db).create_index("solicitud_id", sparse=True)


async def marcar_interrumpidos(db: AsyncIOMotorDatabase, tipos: list[TipoJob]) -> int:
    """Da por fallidos los trabajos de esos tipos que quedaron vivos en Mongo.

    Se llama al arrancar: con un solo worker, un trabajo «en progreso» a esa
    altura murió con el proceso anterior (un reinicio, un despliegue). Sin esto
    quedaba vivo para siempre y bloqueaba el botón que lo lanza.
    """
    resultado = await _col(db).update_many(
        {
            "tipo": {"$in": [t.value for t in tipos]},
            "estado": {"$in": [EstadoJob.PENDIENTE.value, EstadoJob.EN_PROGRESO.value]},
            # Los de la cola durable se recuperan solos (`recuperar_huerfanos`):
            # darlos por fallidos perdería justo lo que la cola viene a salvar.
            "gestionado": {"$ne": True},
        },
        {"$set": {
            "estado": EstadoJob.FALLIDO.value,
            "error": "Interrumpido por un reinicio de la API; vuelve a lanzarlo",
            "actualizado_en": datetime.now(UTC),
        }},
    )
    return resultado.modified_count


def a_documento(job: Job) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "tipo": job.tipo.value,
        "estado": job.estado.value,
        "ruc": job.ruc,
        "periodo": job.periodo,
        "libro": job.libro.value if job.libro else None,
        "progreso": job.progreso.model_dump(),
        "resultado": job.resultado,
        "error": job.error,
        "creado_en": job.creado_en,
        "actualizado_en": job.actualizado_en,
        "gestionado": job.gestionado,
        "cola": job.cola,
        "parametros": job.parametros,
        "solicitud_id": job.solicitud_id,
        "intentos": job.intentos,
        "max_intentos": job.max_intentos,
        "ultimo_intento_en": job.ultimo_intento_en,
        "siguiente_intento_en": job.siguiente_intento_en,
        "latido_en": job.latido_en,
        "historial_errores": job.historial_errores,
    }


def _utc(valor: datetime | None) -> datetime | None:
    """Mongo devuelve las fechas sin zona; son UTC y así se marcan.

    Sin esto la API las serializa sin `Z` y el navegador las lee como hora
    local: en Lima, cinco horas adelantadas.
    """
    if valor is None or valor.tzinfo is not None:
        return valor
    return valor.replace(tzinfo=UTC)


def desde_documento(documento: dict[str, Any]) -> Job:
    return Job(
        job_id=documento["job_id"],
        tipo=documento["tipo"],
        estado=documento["estado"],
        ruc=documento["ruc"],
        periodo=documento["periodo"],
        libro=documento.get("libro"),
        progreso=Progreso(**(documento.get("progreso") or {})),
        resultado=documento.get("resultado"),
        error=documento.get("error"),
        creado_en=_utc(documento["creado_en"]),
        actualizado_en=_utc(documento["actualizado_en"]),
        # Los documentos de antes de la cola no tienen estos campos.
        gestionado=documento.get("gestionado", False),
        cola=documento.get("cola"),
        parametros=documento.get("parametros") or {},
        solicitud_id=documento.get("solicitud_id"),
        intentos=documento.get("intentos", 0),
        max_intentos=documento.get("max_intentos", 1),
        ultimo_intento_en=_utc(documento.get("ultimo_intento_en")),
        siguiente_intento_en=_utc(documento.get("siguiente_intento_en")),
        latido_en=_utc(documento.get("latido_en")),
        historial_errores=documento.get("historial_errores") or [],
    )


async def crear(db: AsyncIOMotorDatabase, job: Job) -> Job:
    await _col(db).insert_one(a_documento(job))
    return job


async def obtener(db: AsyncIOMotorDatabase, job_id: str) -> Job | None:
    documento = await _col(db).find_one({"job_id": job_id})
    return desde_documento(documento) if documento else None


async def listar(
    db: AsyncIOMotorDatabase,
    ruc: str | None = None,
    *,
    periodo: str | None = None,
    libro: Libro | None = None,
    tipo: TipoJob | None = None,
    estado: EstadoJob | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[Job]:
    """Historial de trabajos, del mas reciente al mas antiguo.

    Sin `ruc` devuelve el de todas las empresas: el panel ya no es de una sola.
    """
    filtro: dict[str, Any] = {"ruc": ruc} if ruc else {}
    if periodo:
        filtro["periodo"] = periodo
    if libro:
        filtro["libro"] = libro.value
    if tipo:
        filtro["tipo"] = tipo.value
    if estado:
        filtro["estado"] = estado.value

    cursor = _col(db).find(filtro).sort("creado_en", -1).skip(skip).limit(limit)
    return [desde_documento(documento) async for documento in cursor]


async def actualizar(
    db: AsyncIOMotorDatabase,
    job_id: str,
    *,
    estado: EstadoJob | None = None,
    progreso: Progreso | None = None,
    resultado: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    cambios: dict[str, Any] = {"actualizado_en": datetime.now(UTC)}
    if estado is not None:
        cambios["estado"] = estado.value
    if progreso is not None:
        cambios["progreso"] = progreso.model_dump()
    if resultado is not None:
        cambios["resultado"] = resultado
    if error is not None:
        cambios["error"] = error
    await _col(db).update_one({"job_id": job_id}, {"$set": cambios})


# --- Cola durable ------------------------------------------------------------
#
# El worker (`app.services.cola.worker`) solo habla con Mongo a través de estas
# funciones. Cada una es una única operación atómica: tomar un job y marcarlo
# «en progreso» no puede partirse en leer y luego escribir, o dos corrutinas se
# llevarían el mismo.


async def tomar(
    db: AsyncIOMotorDatabase, carriles_ocupados: set[str], ahora: datetime
) -> Job | None:
    """El pendiente más antiguo cuyo turno ya llegó y cuyo carril está libre."""
    filtro: dict[str, Any] = {
        "gestionado": True,
        "estado": EstadoJob.PENDIENTE.value,
        "$or": [
            {"siguiente_intento_en": None},
            {"siguiente_intento_en": {"$lte": ahora}},
        ],
    }
    if carriles_ocupados:
        # `$nin` deja pasar los documentos con `cola: None`: los que no tienen
        # carril nunca esperan a nadie.
        filtro["cola"] = {"$nin": sorted(carriles_ocupados)}
    documento = await _col(db).find_one_and_update(
        filtro,
        {
            "$set": {
                "estado": EstadoJob.EN_PROGRESO.value,
                "ultimo_intento_en": ahora,
                "latido_en": ahora,
                "actualizado_en": ahora,
                "error": None,
            },
            "$inc": {"intentos": 1},
        },
        sort=[("creado_en", 1)],
        return_document=ReturnDocument.AFTER,
    )
    return desde_documento(documento) if documento else None


async def latir(db: AsyncIOMotorDatabase, job_id: str) -> None:
    await _col(db).update_one(
        {"job_id": job_id, "estado": EstadoJob.EN_PROGRESO.value},
        {"$set": {"latido_en": datetime.now(UTC)}},
    )


async def reprogramar(
    db: AsyncIOMotorDatabase,
    job_id: str,
    *,
    error: str,
    siguiente_intento_en: datetime,
    registro_error: dict[str, Any],
) -> None:
    """Un intento falló por algo pasajero: vuelve a la cola con espera."""
    await _col(db).update_one(
        {"job_id": job_id},
        {
            "$set": {
                "estado": EstadoJob.PENDIENTE.value,
                "error": error,
                "siguiente_intento_en": siguiente_intento_en,
                "actualizado_en": datetime.now(UTC),
            },
            "$push": {"historial_errores": registro_error},
        },
    )


async def finalizar(
    db: AsyncIOMotorDatabase,
    job_id: str,
    estado: EstadoJob,
    *,
    resultado: dict[str, Any] | None = None,
    error: str | None = None,
    registro_error: dict[str, Any] | None = None,
) -> None:
    cambios: dict[str, Any] = {
        "estado": estado.value,
        "actualizado_en": datetime.now(UTC),
        "siguiente_intento_en": None,
    }
    if resultado is not None:
        cambios["resultado"] = resultado
    if error is not None:
        cambios["error"] = error
    operacion: dict[str, Any] = {"$set": cambios}
    if registro_error is not None:
        operacion["$push"] = {"historial_errores": registro_error}
    await _col(db).update_one({"job_id": job_id}, operacion)


async def recuperar_huerfanos(db: AsyncIOMotorDatabase, latido_limite: datetime) -> int:
    """Vuelve a la cola los jobs gestionados cuyo worker dejó de latir.

    Un job «en progreso» sin latido desde `latido_limite` murió con su proceso
    (reinicio, despliegue). Si aún le quedan intentos vuelve a `pendiente`; si
    no, queda fallido. Solo se miran los `gestionado`: el Mongo local lo
    comparte otra copia de la API, y sus jobs no son de este worker.
    """
    ahora = datetime.now(UTC)
    base = {
        "gestionado": True,
        "estado": EstadoJob.EN_PROGRESO.value,
        "latido_en": {"$lt": latido_limite},
    }
    registro = {"en": ahora, "error": "Interrumpido por un reinicio de la API"}
    con_intentos = await _col(db).update_many(
        {**base, "$expr": {"$lt": ["$intentos", "$max_intentos"]}},
        {
            "$set": {
                "estado": EstadoJob.PENDIENTE.value,
                "siguiente_intento_en": ahora,
                "actualizado_en": ahora,
                "progreso.mensaje": "Recuperado tras un reinicio: vuelve a la cola",
            },
            "$push": {"historial_errores": registro},
        },
    )
    agotados = await _col(db).update_many(
        base,
        {
            "$set": {
                "estado": EstadoJob.FALLIDO.value,
                "error": "Interrumpido por un reinicio de la API y sin intentos restantes",
                "actualizado_en": ahora,
            },
            "$push": {"historial_errores": registro},
        },
    )
    return con_intentos.modified_count + agotados.modified_count


async def reintentar(db: AsyncIOMotorDatabase, job_id: str) -> Job | None:
    """Un job gestionado y fallido vuelve a la cola con los intentos a cero."""
    ahora = datetime.now(UTC)
    documento = await _col(db).find_one_and_update(
        {"job_id": job_id, "gestionado": True, "estado": EstadoJob.FALLIDO.value},
        {
            "$set": {
                "estado": EstadoJob.PENDIENTE.value,
                "intentos": 0,
                "error": None,
                "siguiente_intento_en": ahora,
                "actualizado_en": ahora,
                "progreso.mensaje": "Reintento pedido a mano",
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return desde_documento(documento) if documento else None


async def listar_de_solicitud(db: AsyncIOMotorDatabase, solicitud_id: str) -> list[Job]:
    cursor = _col(db).find({"solicitud_id": solicitud_id}).sort("creado_en", 1)
    return [desde_documento(documento) async for documento in cursor]


async def resumen_por_ruc(db: AsyncIOMotorDatabase, desde: datetime) -> dict[str, dict[str, Any]]:
    """Por empresa: su último job, cuántos hay por estado y la última descarga SIRE.

    Los vivos (pendientes y en progreso) se cuentan todos; los terminados, solo
    desde `desde`, para que el panel hable de actividad reciente.
    """
    vivos = [EstadoJob.PENDIENTE.value, EstadoJob.EN_PROGRESO.value]
    tuberia = [
        {"$sort": {"creado_en": -1}},
        {
            "$group": {
                "_id": "$ruc",
                "ultimo": {"$first": "$$ROOT"},
                "estados": {
                    "$push": {
                        "$cond": [
                            {"$or": [
                                {"$in": ["$estado", vivos]},
                                {"$gte": ["$creado_en", desde]},
                            ]},
                            "$estado",
                            "$$REMOVE",
                        ]
                    }
                },
                "ultima_sire": {
                    "$max": {
                        "$cond": [
                            {"$and": [
                                {"$eq": ["$tipo", TipoJob.SINCRONIZACION_SIRE.value]},
                                {"$eq": ["$estado", EstadoJob.COMPLETADO.value]},
                            ]},
                            "$actualizado_en",
                            None,
                        ]
                    }
                },
            }
        },
    ]
    resumen: dict[str, dict[str, Any]] = {}
    async for fila in _col(db).aggregate(tuberia):
        conteo = {estado.value: 0 for estado in EstadoJob}
        for estado in fila.get("estados") or []:
            if estado in conteo:
                conteo[estado] += 1
        resumen[fila["_id"]] = {
            "ultimo": desde_documento(fila["ultimo"]),
            "procesos_por_estado": conteo,
            "ultima_actualizacion_sire": _utc(fila.get("ultima_sire")),
        }
    return resumen


async def ultima_sincronizacion_sire(
    db: AsyncIOMotorDatabase, ruc: str, periodo: str
) -> datetime | None:
    """Cuándo se bajó por última vez desde SIRE ese periodo de esa empresa."""
    documento = await _col(db).find_one(
        {
            "ruc": ruc,
            "periodo": periodo,
            "tipo": TipoJob.SINCRONIZACION_SIRE.value,
            "estado": EstadoJob.COMPLETADO.value,
        },
        sort=[("actualizado_en", -1)],
        projection={"actualizado_en": 1},
    )
    return _utc(documento["actualizado_en"]) if documento else None
