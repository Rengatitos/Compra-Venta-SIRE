from __future__ import annotations

from typing import Any

from bson.decimal128 import Decimal128
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import empresas as repo_empresas
from app.repositories._mongo import NOMBRE_COL_COMPROBANTES, monto_a_float


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_COMPROBANTES]


# Un comprobante en dólares no se puede sumar con uno en soles: hasta ahora los
# totales del dashboard hacían justo eso y devolvían un número que no era ni
# una cosa ni la otra. El registro se lleva en moneda nacional, así que los
# importes se convierten con el tipo de cambio del propio comprobante —el que
# SUNAT declaró para esa operación— antes de agregarlos.
_UNO = Decimal128("1")

# Un comprobante ya está en soles si su moneda es PEN o si no trae ninguna.
_ES_MONEDA_NACIONAL = {"$in": [{"$ifNull": ["$moneda", "PEN"]}, ["PEN", ""]]}

# Un tipo de cambio ausente o en cero no sirve para convertir.
_TIENE_TIPO_CAMBIO = {"$gt": [{"$ifNull": ["$tipo_cambio", 0]}, 0]}

_FACTOR_A_SOLES = {
    "$cond": [
        _ES_MONEDA_NACIONAL,
        _UNO,
        {"$cond": [_TIENE_TIPO_CAMBIO, "$tipo_cambio", _UNO]},
    ]
}

# En moneda extranjera y sin tipo de cambio no hay conversión posible. El
# importe se suma tal cual —dejarlo fuera descuadraría el total contra el
# número de comprobantes—, pero se cuenta aparte para que el dashboard pueda
# avisar de que ese total se queda corto.
_SIN_TIPO_CAMBIO = {
    "$and": [{"$not": [_ES_MONEDA_NACIONAL]}, {"$not": [_TIENE_TIPO_CAMBIO]}]
}


def _en_soles(campo: str) -> dict[str, Any]:
    return {"$multiply": [{"$ifNull": [f"${campo}", 0]}, _FACTOR_A_SOLES]}


def build_match_filter(
    empresa_ids: list[str],
    periodo: str,
    libro: Libro,
    extra: dict[str, Any] | None = None,
) -> dict:
    filtro: dict[str, Any] = {
        "empresa_id": {"$in": empresa_ids},
        "periodo": periodo,
        "libro": libro.value,
    }
    if extra:
        filtro.update(extra)
    return filtro


async def get_target_empresa_ids(
    rucs: str | None, db: AsyncIOMotorDatabase
) -> list[str]:
    if not rucs:
        return []
    lista = [r.strip() for r in rucs.split(",") if r.strip()]
    if not lista:
        return []
    return await repo_empresas.listar_ids_por_rucs(db, lista)


async def get_summary(
    empresa_ids: list[str], periodo: str, libro: Libro, db: AsyncIOMotorDatabase
) -> dict:
    filtro = build_match_filter(empresa_ids, periodo, libro)

    pipeline_totales = [
        {"$match": filtro},
        {
            "$group": {
                "_id": None,
                "total_comprobantes": {"$sum": 1},
                "total_monto": {"$sum": _en_soles("total")},
                "total_igv": {"$sum": _en_soles("igv")},
                "sin_tipo_cambio": {"$sum": {"$cond": [_SIN_TIPO_CAMBIO, 1, 0]}},
            }
        },
    ]
    pipeline_procesadas = [
        {"$match": filtro},
        {
            "$group": {
                "_id": {
                    "$cond": [
                        {"$gt": ["$metadata_procesada.resultado", None]},
                        "procesada",
                        "pendiente",
                    ]
                },
                "count": {"$sum": 1},
            }
        },
    ]

    res_totales = await _col(db).aggregate(pipeline_totales).to_list(1)
    res_procesadas = await _col(db).aggregate(pipeline_procesadas).to_list(None)

    totales = res_totales[0] if res_totales else {}

    procesadas = 0
    pendientes = 0
    for item in res_procesadas:
        if item["_id"] == "procesada":
            procesadas = item["count"]
        else:
            pendientes += item["count"]

    return {
        "total_comprobantes": totales.get("total_comprobantes", 0),
        # Siempre en soles, vengan como vengan los comprobantes.
        "moneda": "PEN",
        "total_monto": monto_a_float(totales.get("total_monto")),
        "total_igv": monto_a_float(totales.get("total_igv")),
        "sin_tipo_cambio": totales.get("sin_tipo_cambio", 0),
        "procesadas": procesadas,
        "pendientes": pendientes,
    }


async def get_top_contrapartes(
    empresa_ids: list[str],
    periodo: str,
    limit: int,
    libro: Libro,
    db: AsyncIOMotorDatabase,
) -> list:
    filtro = build_match_filter(
        empresa_ids,
        periodo,
        libro,
        extra={"razon_social": {"$ne": "", "$exists": True}},
    )
    pipeline = [
        {"$match": filtro},
        {"$group": {"_id": "$razon_social", "total_monto": {"$sum": _en_soles("total")}}},
        {"$sort": {"total_monto": -1}},
        {"$limit": limit},
    ]
    filas = await _col(db).aggregate(pipeline).to_list(limit)
    return [{"name": f["_id"], "total": monto_a_float(f["total_monto"])} for f in filas]


async def get_ai_classification(
    empresa_ids: list[str], periodo: str, libro: Libro, db: AsyncIOMotorDatabase
) -> list:
    filtro = build_match_filter(
        empresa_ids,
        periodo,
        libro,
        extra={"metadata_procesada.resultado": {"$exists": True, "$ne": None}},
    )
    pipeline = [
        {"$match": filtro},
        {"$group": {"_id": "$metadata_procesada.resultado", "value": {"$sum": 1}}},
    ]
    filas = await _col(db).aggregate(pipeline).to_list(None)

    conteos = {"GASTO": 0, "COSTO": 0, "MIXTO": 0, "OTROS": 0}
    for item in filas:
        nombre = str(item.get("_id", "")).upper()
        if "GASTO" in nombre:
            conteos["GASTO"] += item["value"]
        elif "COSTO" in nombre:
            conteos["COSTO"] += item["value"]
        elif "MIXTO" in nombre:
            conteos["MIXTO"] += item["value"]
        else:
            conteos["OTROS"] += item["value"]

    return [{"name": k, "value": v} for k, v in conteos.items() if v > 0]


async def get_comprobantes_by_day(
    empresa_ids: list[str], periodo: str, libro: Libro, db: AsyncIOMotorDatabase
) -> list:
    filtro = build_match_filter(
        empresa_ids, periodo, libro, extra={"fecha_emision": {"$ne": None}}
    )
    pipeline = [
        {"$match": filtro},
        {"$group": {"_id": {"$dayOfMonth": "$fecha_emision"}, "qty": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    filas = await _col(db).aggregate(pipeline).to_list(None)
    return [{"name": f"Día {f['_id']:02d}", "qty": f["qty"]} for f in filas]


async def get_comprobantes_list(
    empresa_ids: list[str],
    periodo: str,
    libro: Libro,
    db: AsyncIOMotorDatabase,
    limit: int = 200,
) -> list:
    from app.services.comprobante_service import serializar_lote

    filtro = build_match_filter(empresa_ids, periodo, libro)
    cursor = _col(db).find(filtro).sort("fecha_emision", -1).limit(limit)
    filas = await cursor.to_list(limit)
    return serializar_lote(filas)


async def periodos_disponibles(
    empresa_ids: list[str], db: AsyncIOMotorDatabase
) -> list[str]:
    if not empresa_ids:
        return []
    return await repo_comprobantes.periodos_disponibles(db, empresa_ids)
