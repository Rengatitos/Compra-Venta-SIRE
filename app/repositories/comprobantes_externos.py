"""Comprobantes que llegan de sire-bot (Apaclla Bot).

Viven aparte de `comprobantes` a propósito: no son de SUNAT y la sincronización
de la propuesta nunca los toca. Cuando existe su periodo se copian como una fila
más de `comprobantes` (`app.services.integracion_externos`), y `comprobante_id`
apunta a esa fila, o a la de SUNAT si el periodo ya lo tenía. Los vouchers se
quedan sólo aquí.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.comprobante_externo import ESTADO_RECIBIDO, TipoEvidencia
from app.repositories._mongo import NOMBRE_COL_COMPROBANTES_EXTERNOS


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_COMPROBANTES_EXTERNOS]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    col = _col(db)
    # Reintentos del bot: el mismo `id_externo` nunca crea dos filas.
    await col.create_index(
        [("empresa_id", 1), ("id_externo", 1)], unique=True, name="uniq_externo_id_externo"
    )
    # El mismo voucher (Yape, Plin...) mandado dos veces con otro id_externo.
    await col.create_index(
        [("empresa_id", 1), ("fuente", 1), ("nro_operacion", 1)],
        unique=True,
        name="uniq_externo_operacion",
        partialFilterExpression={"nro_operacion": {"$gt": ""}},
    )
    # La misma boleta o factura mandada dos veces.
    await col.create_index(
        [("empresa_id", 1), ("libro", 1), ("tipo_cp", 1), ("serie", 1), ("numero", 1)],
        unique=True,
        name="uniq_externo_serie_numero",
        partialFilterExpression={"tipo_evidencia": "comprobante"},
    )
    await col.create_index(
        [("empresa_id", 1), ("libro", 1), ("periodo", 1), ("creado_en", -1)],
        name="externos_listado",
    )
    # Los que esperan su periodo: se buscan en cada refresco.
    await col.create_index(
        [("empresa_id", 1), ("estado", 1), ("periodo", 1)], name="externos_pendientes"
    )


def _oid(valor: str) -> ObjectId | None:
    try:
        return ObjectId(valor)
    except Exception:
        return None


async def por_id_externo(
    db: AsyncIOMotorDatabase, empresa_id: str, id_externo: str
) -> dict[str, Any] | None:
    return await _col(db).find_one({"empresa_id": empresa_id, "id_externo": id_externo})


async def insertar(db: AsyncIOMotorDatabase, documento: dict[str, Any]) -> None:
    await _col(db).insert_one(documento)


async def conflicto(
    db: AsyncIOMotorDatabase, empresa_id: str, documento: dict[str, Any]
) -> dict[str, Any] | None:
    """La fila que ya ocupa la clave natural de `documento`, si la hay."""
    if documento.get("nro_operacion"):
        encontrado = await _col(db).find_one(
            {
                "empresa_id": empresa_id,
                "fuente": documento["fuente"],
                "nro_operacion": documento["nro_operacion"],
            }
        )
        if encontrado:
            return encontrado
    if documento.get("tipo_evidencia") == "comprobante":
        return await _col(db).find_one(
            {
                "empresa_id": empresa_id,
                "tipo_evidencia": "comprobante",
                "libro": documento["libro"],
                "tipo_cp": documento["tipo_cp"],
                "serie": documento["serie"],
                "numero": documento["numero"],
            }
        )
    return None


def _filtro(
    empresa_id: str, libro: str | None, periodo: str | None, fuente: str | None
) -> dict[str, Any]:
    filtro: dict[str, Any] = {"empresa_id": empresa_id}
    if libro:
        filtro["libro"] = libro
    if periodo:
        filtro["periodo"] = periodo
    if fuente:
        filtro["fuente"] = fuente
    return filtro


async def listar(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    *,
    libro: str | None = None,
    periodo: str | None = None,
    fuente: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[dict[str, Any]], int]:
    filtro = _filtro(empresa_id, libro, periodo, fuente)
    cursor = _col(db).find(filtro).sort("creado_en", -1).skip(skip).limit(limit)
    documentos = await cursor.to_list(length=limit)
    total = await _col(db).count_documents(filtro)
    return documentos, total


async def periodos(
    db: AsyncIOMotorDatabase, empresa_id: str, libro: str | None = None
) -> list[str]:
    filtro = _filtro(empresa_id, libro, None, None)
    valores = await _col(db).distinct("periodo", filtro)
    return sorted((v for v in valores if v), reverse=True)


async def obtener(db: AsyncIOMotorDatabase, empresa_id: str, id_: str) -> dict[str, Any] | None:
    oid = _oid(id_)
    if oid is None:
        return None
    return await _col(db).find_one({"_id": oid, "empresa_id": empresa_id})


async def pendientes(
    db: AsyncIOMotorDatabase, empresa_id: str, periodos: list[str] | None = None
) -> list[dict[str, Any]]:
    """Los que esperan su periodo. Los vouchers no: nunca pasan a él."""
    filtro: dict[str, Any] = {
        "empresa_id": empresa_id,
        "estado": ESTADO_RECIBIDO,
        "tipo_evidencia": {"$ne": TipoEvidencia.VOUCHER.value},
    }
    if periodos is not None:
        filtro["periodo"] = {"$in": periodos}
    return await _col(db).find(filtro).sort("creado_en", 1).to_list(length=None)


async def marcar(
    db: AsyncIOMotorDatabase, documento_id, estado: str, comprobante_id: str | None
) -> None:
    await _col(db).update_one(
        {"_id": documento_id},
        {
            "$set": {
                "estado": estado,
                "comprobante_id": comprobante_id,
                "integrado_en": datetime.now(UTC),
            }
        },
    )


async def devolver_a_pendiente(db: AsyncIOMotorDatabase, empresa_id: str, periodo: str) -> int:
    """Al borrar un periodo sus externos vuelven a esperar a que se cree otra vez."""
    resultado = await _col(db).update_many(
        {"empresa_id": empresa_id, "periodo": periodo, "estado": {"$ne": ESTADO_RECIBIDO}},
        {"$set": {"estado": ESTADO_RECIBIDO, "comprobante_id": None, "integrado_en": None}},
    )
    return resultado.modified_count


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count
