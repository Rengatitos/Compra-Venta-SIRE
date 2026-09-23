"""Clasificaciones frecuentes por empresa y libro (`app.domain.glosa_similar`).

Una entrada por glosa distinta (su `clave`): la cuenta que se le asignó, de
dónde salió (`ia` o `usuario`) y cuántas veces se reutilizó. Solo se reutilizan
las `confiables`: las que la IA clasificó sin pedir revisión y las que un
usuario confirmó o corrigió.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories._mongo import NOMBRE_COL_CLASIFICACIONES_FRECUENTES


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_CLASIFICACIONES_FRECUENTES]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index(
        [("empresa_id", 1), ("libro", 1), ("clave", 1)], unique=True, name="uniq_glosa"
    )


def _oid(entrada_id: str) -> ObjectId | None:
    try:
        return ObjectId(entrada_id)
    except Exception:
        return None


async def listar(
    db: AsyncIOMotorDatabase, empresa_id: str, libro: str | None = None,
    solo_confiables: bool = False,
) -> list[dict[str, Any]]:
    filtro: dict[str, Any] = {"empresa_id": empresa_id}
    if libro:
        filtro["libro"] = libro
    if solo_confiables:
        filtro["confiable"] = True
    return await _col(db).find(filtro).sort([("usos", -1), ("actualizado_en", -1)]).to_list(
        length=None
    )


async def obtener(db: AsyncIOMotorDatabase, empresa_id: str, entrada_id: str) -> dict | None:
    oid = _oid(entrada_id)
    if oid is None:
        return None
    return await _col(db).find_one({"_id": oid, "empresa_id": empresa_id})


async def registrar_de_ia(
    db: AsyncIOMotorDatabase, empresa_id: str, libro: str, clave: str, glosa: str,
    clasificacion: dict[str, Any],
) -> ObjectId:
    """Guarda (o refresca) lo que la IA dijo para esta glosa.

    Nunca pisa una entrada que un usuario ya corrigió: su palabra manda.
    """
    ahora = datetime.now(UTC)
    campos = {
        "cuenta_base": clasificacion.get("cuenta_base"),
        "cuenta_total": clasificacion.get("cuenta_total"),
        "clasificacion": clasificacion.get("clasificacion", ""),
        "subtipo": clasificacion.get("subtipo", ""),
        "confianza": clasificacion.get("confianza", 0.0),
        "confiable": not clasificacion.get("requiere_revision", True),
        "origen": "ia",
        # El razonamiento de la IA, para explicar la cuenta cada vez que se
        # reutilice (`clasificacion_service.resumir_motivo`).
        "razon": clasificacion.get("razon_ia") or clasificacion.get("razon", ""),
        "actualizado_en": ahora,
    }
    existente = await _col(db).find_one(
        {"empresa_id": empresa_id, "libro": libro, "clave": clave},
        {"origen": 1, "razon": 1, "confiable": 1},
    )
    # Ni la cuenta que fijó un usuario ni una confiable se pisan con una
    # respuesta dudosa de la IA; solo se completa el motivo si faltaba.
    protegida = existente and (
        existente.get("origen") == "usuario"
        or (existente.get("confiable") and not campos["confiable"])
    )
    if protegida:
        if not existente.get("razon") and campos["razon"]:
            await _col(db).update_one(
                {"_id": existente["_id"]}, {"$set": {"razon": campos["razon"]}}
            )
        return existente["_id"]
    resultado = await _col(db).find_one_and_update(
        {"empresa_id": empresa_id, "libro": libro, "clave": clave},
        {
            "$set": campos,
            "$setOnInsert": {"glosa": glosa, "usos": 0, "creado_en": ahora},
        },
        upsert=True,
        return_document=True,
        projection={"_id": 1},
    )
    return resultado["_id"]


async def contar_uso(db: AsyncIOMotorDatabase, entrada_id: ObjectId) -> None:
    await _col(db).update_one(
        {"_id": entrada_id},
        {"$inc": {"usos": 1}, "$set": {"ultimo_uso": datetime.now(UTC)}},
    )


async def corregir(
    db: AsyncIOMotorDatabase, empresa_id: str, entrada_id: str, cambios: dict[str, Any],
    por: str,
) -> dict | None:
    """Corrección de un usuario: pasa a ser confiable y de origen `usuario`."""
    oid = _oid(entrada_id)
    if oid is None:
        return None
    return await _col(db).find_one_and_update(
        {"_id": oid, "empresa_id": empresa_id},
        {"$set": {
            **cambios,
            "origen": "usuario",
            "confiable": True,
            "corregido_por": por,
            "actualizado_en": datetime.now(UTC),
        }},
        return_document=True,
    )


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count


async def eliminar(db: AsyncIOMotorDatabase, empresa_id: str, entrada_id: str) -> bool:
    oid = _oid(entrada_id)
    if oid is None:
        return False
    resultado = await _col(db).delete_one({"_id": oid, "empresa_id": empresa_id})
    return resultado.deleted_count > 0
