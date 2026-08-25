from typing import Any, Dict, List, Optional


def build_match_filter(user_ids: List[str], periodo: str, tipo_operacion: str, extra: Optional[Dict[str, Any]] = None) -> dict:
    filtro = {
        "user_id": {"$in": user_ids},
        "periodo": periodo,
        "$or": [{"tipo_operacion": tipo_operacion}, {"tipo_operacion": {"$exists": False}}],
    }
    if extra:
        filtro.update(extra)
    return filtro


async def get_target_user_ids(rucs: Optional[str], db, token_payload: dict) -> List[str]:
    sol_users_col = db["sol_users"]

    if not rucs:
        return []

    ruc_list = [r.strip() for r in rucs.split(",") if r.strip()]
    if not ruc_list:
        return []

    target_users = await sol_users_col.find({"ruc": {"$in": ruc_list}}).to_list(None)
    return [str(u["_id"]) for u in target_users]


async def get_summary(user_ids: List[str], periodo: str, tipo_operacion: str, db) -> dict:
    facturas_col = db["facturas"]
    match_filter = build_match_filter(user_ids, periodo, tipo_operacion)

    pipeline_totales = [
        {"$match": match_filter},
        {"$group": {
            "_id": None,
            "total_invoices": {"$sum": 1},
            "total_monto": {"$sum": "$total"},
            "total_igv": {"$sum": "$igv"}
        }}
    ]
    pipeline_procesadas = [
        {"$match": match_filter},
        {"$group": {
            "_id": {"$cond": [{"$gt": ["$metadata_procesada.resultado", None]}, "procesada", "pendiente"]},
            "count": {"$sum": 1}
        }}
    ]

    res_totales = await facturas_col.aggregate(pipeline_totales).to_list(1)
    res_procesadas = await facturas_col.aggregate(pipeline_procesadas).to_list(None)

    totales = res_totales[0] if res_totales else {"total_invoices": 0, "total_monto": 0, "total_igv": 0}

    if not totales.get("total_igv") and totales.get("total_monto", 0) > 0:
        totales["total_igv"] = totales["total_monto"] - (totales["total_monto"] / 1.18)

    procesadas_count = 0
    pendientes_count = 0
    for p in res_procesadas:
        if p["_id"] == "procesada":
            procesadas_count = p["count"]
        else:
            pendientes_count += p["count"]

    return {
        "total_invoices": totales.get("total_invoices", 0),
        "total_monto": totales.get("total_monto", 0),
        "total_igv": totales.get("total_igv", 0),
        "procesadas": procesadas_count,
        "pendientes": pendientes_count
    }


async def get_top_suppliers(user_ids: List[str], periodo: str, limit: int, tipo_operacion: str, db) -> list:
    facturas_col = db["facturas"]
    match_filter = build_match_filter(
        user_ids, periodo, tipo_operacion,
        extra={"nombre_proveedor": {"$ne": "", "$exists": True}},
    )
    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$nombre_proveedor",
            "total_monto": {"$sum": "$total"}
        }},
        {"$sort": {"total_monto": -1}},
        {"$limit": limit},
        {"$project": {
            "_id": 0,
            "name": "$_id",
            "total": "$total_monto"
        }}
    ]
    return await facturas_col.aggregate(pipeline).to_list(limit)


async def get_ai_classification(user_ids: List[str], periodo: str, tipo_operacion: str, db) -> list:
    facturas_col = db["facturas"]
    match_filter = build_match_filter(
        user_ids, periodo, tipo_operacion,
        extra={"metadata_procesada.resultado": {"$exists": True, "$ne": None}},
    )
    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$metadata_procesada.resultado",
            "value": {"$sum": 1}
        }},
        {"$project": {
            "_id": 0,
            "name": "$_id",
            "value": 1
        }}
    ]
    res = await facturas_col.aggregate(pipeline).to_list(None)
    counts = {"GASTO": 0, "COSTO": 0, "MIXTO": 0, "OTROS": 0}
    for item in res:
        name = str(item.get("name", "")).upper()
        if "GASTO" in name:
            counts["GASTO"] += item["value"]
        elif "COSTO" in name:
            counts["COSTO"] += item["value"]
        elif "MIXTO" in name:
            counts["MIXTO"] += item["value"]
        else:
            counts["OTROS"] += item["value"]

    return [{"name": k, "value": v} for k, v in counts.items() if v > 0]


async def get_invoices_by_day(user_ids: List[str], periodo: str, tipo_operacion: str, db) -> list:
    facturas_col = db["facturas"]
    match_filter = build_match_filter(user_ids, periodo, tipo_operacion)
    pipeline = [
        {"$match": match_filter},
        {"$project": {
            "dia": {"$substr": ["$fecha_emision", 0, 2]}
        }},
        {"$group": {
            "_id": "$dia",
            "qty": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    res = await facturas_col.aggregate(pipeline).to_list(None)
    final_res = []
    for item in res:
        dia = item["_id"]
        if dia and "-" in dia:
            continue
        final_res.append({
            "name": f"Día {dia}",
            "qty": item["qty"]
        })
    return sorted(final_res, key=lambda x: x["name"])


async def get_invoices_list(user_ids: List[str], periodo: str, tipo_operacion: str, db, limit: int = 200) -> list:
    facturas_col = db["facturas"]
    query = build_match_filter(user_ids, periodo, tipo_operacion)
    cursor = facturas_col.find(query, {"_id": 0, "xml_content": 0, "pdf_content": 0}).sort("fecha_emision", -1).limit(limit)
    return await cursor.to_list(limit)
