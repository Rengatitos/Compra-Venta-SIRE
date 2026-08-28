from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.comprobante import (
    Comprobante,
    EstadoProcesamiento,
    Libro,
    Origen,
)
from app.repositories._mongo import (
    NOMBRE_COL_COMPROBANTES,
    fecha_a_bson,
    fecha_desde_bson,
    monto_a_bson,
    monto_desde_bson,
)

_CAMPOS_MONTO = (
    "base_imponible",
    "igv",
    "exonerado",
    "inafecto",
    "isc",
    "otros_tributos",
    "total",
)


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_COMPROBANTES]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    col = _col(db)
    await col.create_index([("empresa_id", 1), ("periodo", 1)])
    await col.create_index(
        [
            ("empresa_id", 1),
            ("periodo", 1),
            ("libro", 1),
            ("origen", 1),
            ("tipo_cp", 1),
            ("serie", 1),
            ("numero", 1),
        ],
        unique=True,
        name="uniq_comprobante",
    )


def a_documento(comprobante: Comprobante, empresa_id: str, periodo: str) -> dict[str, Any]:
    documento: dict[str, Any] = {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "libro": comprobante.libro.value,
        "origen": comprobante.origen.value,
        "tipo_cp": comprobante.tipo_cp,
        "serie": comprobante.serie,
        "numero": comprobante.numero,
        "serie_numero": comprobante.serie_numero,
        "tipo_doc_identidad": comprobante.tipo_doc_identidad,
        "documento_contraparte": comprobante.documento_contraparte,
        "razon_social": comprobante.razon_social,
        "fecha_emision": fecha_a_bson(comprobante.fecha_emision),
        "fecha_vencimiento": fecha_a_bson(comprobante.fecha_vencimiento),
        "moneda": comprobante.moneda,
        "tipo_cambio": monto_a_bson(comprobante.tipo_cambio),
        "extra": comprobante.extra,
    }
    for campo in _CAMPOS_MONTO:
        documento[campo] = monto_a_bson(getattr(comprobante, campo))
    return documento


def desde_documento(documento: dict[str, Any]) -> Comprobante:
    montos = {campo: monto_desde_bson(documento.get(campo)) for campo in _CAMPOS_MONTO}
    tipo_cambio = documento.get("tipo_cambio")
    return Comprobante(
        libro=Libro(documento.get("libro", Libro.COMPRAS.value)),
        origen=Origen(documento.get("origen", Origen.SIRE.value)),
        tipo_cp=documento.get("tipo_cp", ""),
        serie=documento.get("serie", ""),
        numero=documento.get("numero", ""),
        tipo_doc_identidad=documento.get("tipo_doc_identidad", ""),
        documento_contraparte=documento.get("documento_contraparte", ""),
        razon_social=documento.get("razon_social", ""),
        fecha_emision=fecha_desde_bson(documento.get("fecha_emision")),
        fecha_vencimiento=fecha_desde_bson(documento.get("fecha_vencimiento")),
        moneda=documento.get("moneda", "PEN"),
        tipo_cambio=monto_desde_bson(tipo_cambio) if tipo_cambio is not None else None,
        extra=documento.get("extra", {}),
        **montos,
    )


def filtro_identidad(
    empresa_id: str, periodo: str, comprobante: Comprobante
) -> dict[str, Any]:
    return {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "libro": comprobante.libro.value,
        "origen": comprobante.origen.value,
        "tipo_cp": comprobante.tipo_cp,
        "serie": comprobante.serie,
        "numero": comprobante.numero,
    }


async def upsert(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, comprobante: Comprobante
) -> bool:
    documento = a_documento(comprobante, empresa_id, periodo)
    resultado = await _col(db).update_one(
        filtro_identidad(empresa_id, periodo, comprobante),
        {
            "$setOnInsert": {"estado_procesamiento": EstadoProcesamiento.SIRE_RECIBIDO.value},
            "$set": documento,
        },
        upsert=True,
    )
    return resultado.upserted_id is not None


async def listar(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    skip: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    cursor = _col(db).find({"empresa_id": empresa_id, "periodo": periodo}).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def obtener(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, serie_numero: str
) -> dict[str, Any] | None:
    return await _col(db).find_one(
        {"empresa_id": empresa_id, "periodo": periodo, "serie_numero": serie_numero}
    )


async def listar_pendientes_analisis(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, limit: int = 1000
) -> list[dict[str, Any]]:
    pendientes = [EstadoProcesamiento.SIRE_RECIBIDO.value, EstadoProcesamiento.ERROR_ANALISIS.value]
    cursor = (
        _col(db)
        .find(
            {
                "empresa_id": empresa_id,
                "periodo": periodo,
                "$or": [
                    {"estado_procesamiento": {"$in": pendientes}},
                    {"estado_procesamiento": {"$exists": False}},
                ],
            }
        )
        .sort([("_id", -1)])
    )
    return await cursor.to_list(length=limit)


async def listar_sin_detalle(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, limit: int = 100
) -> list[dict[str, Any]]:
    cursor = _col(db).find(
        {
            "empresa_id": empresa_id,
            "periodo": periodo,
            "detalle_sunat": {"$exists": False},
        }
    )
    return await cursor.to_list(length=limit)


async def guardar_analisis(
    db: AsyncIOMotorDatabase,
    documento_id: Any,
    metadata: dict[str, Any],
    estado: EstadoProcesamiento,
) -> None:
    await _col(db).update_one(
        {"_id": documento_id},
        {"$set": {"metadata_procesada": metadata, "estado_procesamiento": estado.value}},
    )


async def actualizar_estado(
    db: AsyncIOMotorDatabase, documento_id: Any, estado: EstadoProcesamiento
) -> None:
    await _col(db).update_one(
        {"_id": documento_id}, {"$set": {"estado_procesamiento": estado.value}}
    )


async def guardar_metadata(
    db: AsyncIOMotorDatabase, documento_id: Any, metadata: dict[str, Any]
) -> None:
    await _col(db).update_one({"_id": documento_id}, {"$set": {"metadata_procesada": metadata}})


async def guardar_detalle_sunat(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    serie_numero: str,
    detalle: list[Any],
) -> None:
    await _col(db).update_one(
        {"empresa_id": empresa_id, "periodo": periodo, "serie_numero": serie_numero},
        {"$set": {"detalle_sunat": detalle}},
    )


async def periodos_disponibles(db: AsyncIOMotorDatabase, empresa_ids: list[str]) -> list[str]:
    periodos = await _col(db).distinct("periodo", {"empresa_id": {"$in": empresa_ids}})
    return sorted(periodos, reverse=True)


async def eliminar_de_periodo(db: AsyncIOMotorDatabase, empresa_id: str, periodo: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id, "periodo": periodo})
    return resultado.deleted_count


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count
