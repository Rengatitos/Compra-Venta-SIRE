"""Cuentas de API: correo y contraseña para integraciones (ELT, scripts).

Son para programas, no para personas: entran por `POST /auth/token` sin pasar
por Google. La contraseña la genera Sire y solo se guarda su hash
(`app.core.claves`); vence a los `vigencia_dias` y el administrador la regenera
desde el panel cuando quiera. Tienen acceso completo (rol admin).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.usuario import Rol, normalizar_correo
from app.repositories._mongo import NOMBRE_COL_CUENTAS_API

# Lo que se devuelve al panel: todo menos el hash.
_PROYECCION = {"_id": 0, "clave_hash": 0}


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_CUENTAS_API]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index("email", unique=True)


async def obtener(db: AsyncIOMotorDatabase, correo: str) -> dict[str, Any] | None:
    """Con el hash: solo para comprobar la contraseña."""
    return await _col(db).find_one({"email": normalizar_correo(correo)})


async def listar(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    return await _col(db).find({}, _PROYECCION).sort("email", 1).to_list(length=None)


async def guardar_clave(
    db: AsyncIOMotorDatabase,
    correo: str,
    *,
    clave_hash: str,
    vigencia_dias: int,
    por: str,
) -> dict[str, Any]:
    """Alta o regeneración: la contraseña anterior deja de servir en el acto."""
    correo = normalizar_correo(correo)
    ahora = datetime.now(UTC)
    await _col(db).update_one(
        {"email": correo},
        {
            "$set": {
                "rol": Rol.ADMIN.value,
                "clave_hash": clave_hash,
                "vigencia_dias": vigencia_dias,
                "clave_generada_en": ahora,
                "expira_en": ahora + timedelta(days=vigencia_dias),
                "clave_generada_por": por,
            },
            "$setOnInsert": {"email": correo, "creada_por": por, "creada_en": ahora},
        },
        upsert=True,
    )
    return await _col(db).find_one({"email": correo}, _PROYECCION)


async def marcar_uso(db: AsyncIOMotorDatabase, correo: str) -> None:
    await _col(db).update_one(
        {"email": normalizar_correo(correo)}, {"$set": {"ultimo_uso_en": datetime.now(UTC)}}
    )


async def eliminar(db: AsyncIOMotorDatabase, correo: str) -> bool:
    resultado = await _col(db).delete_one({"email": normalizar_correo(correo)})
    return resultado.deleted_count > 0


def vigente(cuenta: dict[str, Any], ahora: datetime | None = None) -> bool:
    expira = cuenta.get("expira_en")
    if expira is None:
        return False
    if expira.tzinfo is None:  # Mongo devuelve fechas sin zona
        expira = expira.replace(tzinfo=UTC)
    return expira > (ahora or datetime.now(UTC))


async def rol_de(db: AsyncIOMotorDatabase | None, correo: str) -> str | None:
    """`admin` si es una cuenta de API vigente, o `None`.

    Siempre admin, también para las cuentas creadas cuando se elegía el rol.
    """
    if db is None:
        return None
    cuenta = await _col(db).find_one({"email": normalizar_correo(correo)}, {"expira_en": 1})
    if cuenta is None or not vigente(cuenta):
        return None
    return Rol.ADMIN.value
