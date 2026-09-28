"""Configuración del sistema que se edita desde el panel. Un documento por área."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.configuracion_correo import ConfiguracionCorreo, desde_documento
from app.repositories._mongo import NOMBRE_COL_CONFIGURACION

ID_CORREO = "correo"


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_CONFIGURACION]


async def obtener_correo(db: AsyncIOMotorDatabase) -> ConfiguracionCorreo:
    """La configuración guardada o, si nunca se guardó, la de por defecto."""
    return desde_documento(await _col(db).find_one({"_id": ID_CORREO}))


async def guardar_correo(
    db: AsyncIOMotorDatabase, cambios: dict[str, Any], *, por: str
) -> ConfiguracionCorreo:
    await _col(db).update_one(
        {"_id": ID_CORREO},
        {"$set": {**cambios, "actualizado_en": datetime.now(UTC), "actualizado_por": por}},
        upsert=True,
    )
    return await obtener_correo(db)
