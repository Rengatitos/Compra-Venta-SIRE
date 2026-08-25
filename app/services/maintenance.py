async def deduplicate_facturas(db) -> int:
    facturas_col = db["facturas"]
    pipeline = [
        {
            "$group": {
                "_id": {
                    "user_id": "$user_id",
                    "periodo": "$periodo",
                    "serie_numero": "$serie_numero",
                },
                "count": {"$sum": 1},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
    ]

    duplicados = await facturas_col.aggregate(pipeline).to_list(length=20000)
    eliminadas = 0

    for dup in duplicados:
        key = dup["_id"]
        docs = (
            await facturas_col.find(
                {
                    "user_id": key.get("user_id"),
                    "periodo": key.get("periodo"),
                    "serie_numero": key.get("serie_numero"),
                }
            )
            .sort([("_id", -1)])
            .to_list(length=5000)
        )
        if len(docs) <= 1:
            continue
        ids_delete = [doc["_id"] for doc in docs[1:]]
        res = await facturas_col.delete_many({"_id": {"$in": ids_delete}})
        eliminadas += res.deleted_count

    return eliminadas
