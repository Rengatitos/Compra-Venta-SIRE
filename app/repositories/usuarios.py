"""Correos con acceso al panel agregados desde la web (`app.domain.usuario`).

Los administradores fijos de `GOOGLE_ALLOWED_EMAILS` no se guardan aquí: viven
en el entorno y no se pueden tocar desde el panel.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.usuario import Rol, normalizar_correo
from app.repositories._mongo import NOMBRE_COL_USUARIOS


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_USUARIOS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index("email", unique=True)


async def rol_de(db: AsyncIOMotorDatabase | None, correo: str) -> str | None:
    """El rol guardado para ese correo, o `None` si no está registrado."""
    if db is None:
        return None
    documento = await _col(db).find_one({"email": normalizar_correo(correo)}, {"rol": 1})
    return documento.get("rol") if documento else None


async def listar(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    return await _col(db).find({}, {"_id": 0}).sort("email", 1).to_list(length=None)


async def guardar(db: AsyncIOMotorDatabase, correo: str, rol: Rol, por: str) -> dict[str, Any]:
    """Alta o cambio de rol. Devuelve el documento resultante."""
    correo = normalizar_correo(correo)
    ahora = datetime.now(UTC)
    await _col(db).update_one(
        {"email": correo},
        {
            "$set": {"rol": rol.value, "actualizado_por": por, "actualizado_en": ahora},
            "$setOnInsert": {"email": correo, "agregado_por": por, "agregado_en": ahora},
        },
        upsert=True,
    )
    return await _col(db).find_one({"email": correo}, {"_id": 0})


async def eliminar(db: AsyncIOMotorDatabase, correo: str) -> bool:
    resultado = await _col(db).delete_one({"email": normalizar_correo(correo)})
    return resultado.deleted_count > 0


async def contar_admins(db: AsyncIOMotorDatabase) -> int:
    return await _col(db).count_documents({"rol": Rol.ADMIN.value})
