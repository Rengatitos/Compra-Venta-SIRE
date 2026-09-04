from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.plan_cuentas import Cuenta
from app.repositories._mongo import NOMBRE_COL_PLAN_CUENTAS


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_PLAN_CUENTAS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    col = _col(db)
    await col.create_index([("empresa_id", 1), ("cuenta", 1)], unique=True, name="uniq_cuenta")
    # El buscador de la pantalla filtra por descripción, y son ~2.900 cuentas
    # por empresa: sin índice de texto cada tecleo recorre la colección entera.
    await col.create_index([("empresa_id", 1), ("descripcion", 1)])


def a_documento(cuenta: Cuenta, empresa_id: str) -> dict[str, Any]:
    return {"empresa_id": empresa_id, **cuenta.model_dump()}


def desde_documento(documento: dict[str, Any]) -> Cuenta:
    return Cuenta(
        cuenta=documento.get("cuenta", ""),
        descripcion=documento.get("descripcion", ""),
        tipo=documento.get("tipo", ""),
        analisis=documento.get("analisis", ""),
        centro_costos=documento.get("centro_costos", ""),
        nivel=documento.get("nivel", 1),
    )


async def reemplazar(
    db: AsyncIOMotorDatabase, empresa_id: str, cuentas: list[Cuenta]
) -> int:
    """Sustituye el maestro completo de la empresa y devuelve cuántas quedaron.

    Se reemplaza en vez de fusionar porque el archivo es la fuente de verdad:
    una cuenta que Contasis dejó de exportar es una cuenta que ya no existe, y
    fusionando se quedaría viva para siempre.
    """
    await eliminar_de_empresa(db, empresa_id)
    if not cuentas:
        return 0

    documentos = [a_documento(cuenta, empresa_id) for cuenta in cuentas]
    documentos[0]["cargado_en"] = datetime.now(UTC)
    await _col(db).insert_many(documentos)
    return len(documentos)


async def listar(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    busqueda: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    filtro: dict[str, Any] = {"empresa_id": empresa_id}
    if busqueda:
        # Se busca por código y por descripción a la vez: el contador conoce el
        # número de unas cuentas y el nombre de otras.
        patron = {"$regex": _escapar(busqueda), "$options": "i"}
        filtro["$or"] = [{"cuenta": patron}, {"descripcion": patron}]

    cursor = _col(db).find(filtro).sort([("cuenta", 1)]).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def contar(
    db: AsyncIOMotorDatabase, empresa_id: str, busqueda: str | None = None
) -> int:
    filtro: dict[str, Any] = {"empresa_id": empresa_id}
    if busqueda:
        patron = {"$regex": _escapar(busqueda), "$options": "i"}
        filtro["$or"] = [{"cuenta": patron}, {"descripcion": patron}]
    return await _col(db).count_documents(filtro)


async def obtener(
    db: AsyncIOMotorDatabase, empresa_id: str, cuenta: str
) -> dict[str, Any] | None:
    return await _col(db).find_one({"empresa_id": empresa_id, "cuenta": cuenta})


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count


def _escapar(busqueda: str) -> str:
    """Neutraliza la búsqueda como expresión regular.

    Sin esto, un `(` o un `*` que el usuario teclee en el buscador no da un
    filtro raro: hace fallar la consulta entera con un error de Mongo.
    """
    return re.escape(busqueda.strip())
