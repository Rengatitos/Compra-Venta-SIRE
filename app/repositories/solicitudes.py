"""Solicitudes de procesamiento masivo: qué se pidió, cómo va cada item y a
quién se le envió el resultado."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.solicitudes import EstadoSolicitud
from app.repositories._mongo import NOMBRE_COL_SOLICITUDES
from app.repositories.empresas import a_object_id


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_SOLICITUDES]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index([("creado_en", -1)])


async def crear(db: AsyncIOMotorDatabase, documento: dict[str, Any]) -> str:
    resultado = await _col(db).insert_one(documento)
    return str(resultado.inserted_id)


async def obtener(db: AsyncIOMotorDatabase, solicitud_id: str) -> dict[str, Any] | None:
    oid = a_object_id(solicitud_id)
    if oid is None:
        return None
    return await _col(db).find_one({"_id": oid})


async def listar(db: AsyncIOMotorDatabase, limit: int = 30) -> list[dict[str, Any]]:
    cursor = _col(db).find().sort("creado_en", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def actualizar(db: AsyncIOMotorDatabase, solicitud_id: str, cambios: dict[str, Any]) -> None:
    oid = a_object_id(solicitud_id)
    if oid is None:
        return
    await _col(db).update_one(
        {"_id": oid}, {"$set": {**cambios, "actualizado_en": datetime.now(UTC)}}
    )


async def guardar_item(
    db: AsyncIOMotorDatabase, solicitud_id: str, indice: int, item: dict[str, Any]
) -> None:
    await actualizar(db, solicitud_id, {f"items.{indice}": item})


async def reservar_empaquetado(db: AsyncIOMotorDatabase, solicitud_id: str) -> bool:
    """Pasa la solicitud a «empaquetando» si nadie lo hizo antes.

    Dos pasos de items distintos pueden terminar a la vez y ver los dos que ya
    no queda nada: la reserva es atómica para que solo uno encole el ZIP.
    """
    oid = a_object_id(solicitud_id)
    if oid is None:
        return False
    resultado = await _col(db).update_one(
        {"_id": oid, "estado": EstadoSolicitud.EN_PROGRESO.value},
        {"$set": {
            "estado": EstadoSolicitud.EMPAQUETANDO.value,
            "actualizado_en": datetime.now(UTC),
        }},
    )
    return resultado.modified_count == 1


async def guardar_envio(
    db: AsyncIOMotorDatabase, solicitud_id: str, indice: int, cambios: dict[str, Any]
) -> None:
    await actualizar(
        db, solicitud_id, {f"envios.{indice}.{campo}": valor for campo, valor in cambios.items()}
    )


async def listar_envios(db: AsyncIOMotorDatabase, limit: int = 100) -> list[dict[str, Any]]:
    """Los envíos de correo de todas las solicitudes, del más reciente al más antiguo."""
    tuberia = [
        {"$match": {"envios.0": {"$exists": True}}},
        {"$sort": {"creado_en": -1}},
        {"$limit": limit},
        {"$unwind": "$envios"},
        {"$replaceRoot": {"newRoot": {"$mergeObjects": [
            "$envios",
            {"solicitud_id": {"$toString": "$_id"}, "solicitud_creada_en": "$creado_en"},
        ]}}},
        {"$limit": limit},
    ]
    return [documento async for documento in _col(db).aggregate(tuberia)]
