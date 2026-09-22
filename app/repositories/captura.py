"""Persistencia de captura. Todas las lecturas de negocio llevan company_id."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pymongo import ReturnDocument


def now() -> datetime:
    return datetime.now(UTC)


def collection(db, name: str):
    return db["captura_" + name]


async def crear_indices(db) -> None:
    for name in (
        "documents",
        "batches",
        "sessions",
        "phones",
        "events",
        "notifications",
        "matches",
    ):
        await collection(db, name).create_index("company_id")
    await collection(db, "phones").create_index("phone", unique=True)
    await collection(db, "documents").create_index([("company_id", 1), ("accounting_period", 1)])
    await collection(db, "documents").create_index([("company_id", 1), ("file_hash", 1)])
    await collection(db, "documents").create_index([("company_id", 1), ("fingerprint", 1)])
    await collection(db, "documents").create_index([("status", 1), ("lease_until", 1)])
    await collection(db, "documents").create_index("batch_id")
    await collection(db, "events").create_index("message_sid", unique=True)
    await collection(db, "audit").create_index([("company_id", 1), ("document_id", 1)])


def new_document(company_id: str, source: str, **extra) -> dict:
    timestamp = now()
    return {
        "_id": uuid4().hex,
        "company_id": company_id,
        "source": source,
        "status": "QUEUED",
        "batch_id": None,
        "document_date": None,
        "metadata_date": None,
        "accounting_period": None,
        "accounting_year": None,
        "accounting_month": None,
        "period_validation": "UNVERIFIED",
        "period_source": None,
        "received_at": timestamp,
        "created_at": timestamp,
        "updated_at": timestamp,
        "revision": 0,
        "attempts": 0,
        "issues": [],
        "possible_duplicate": False,
        **extra,
    }


async def get(db, name: str, company: str, identifier: str, session=None) -> dict | None:
    return await collection(db, name).find_one(
        {"_id": identifier, "company_id": company}, session=session
    )


async def audit(
    db, company: str, document_id: str, actor: str, action: str, old=None, new=None, session=None
) -> None:
    await collection(db, "audit").insert_one(
        {
            "company_id": company,
            "document_id": document_id,
            "actor": actor,
            "action": action,
            "old_value": old,
            "new_value": new,
            "timestamp": now(),
        },
        session=session,
    )


async def transaction(db, callback):
    # Atlas ya es replica set. No degradar a escrituras parciales si no hay transacciones.
    async with await db.client.start_session() as session:
        return await session.with_transaction(callback)


async def batch_counts(db, company: str, batch_id: str, session=None) -> dict:
    rows = (
        await collection(db, "documents")
        .aggregate(
            [
                {"$match": {"company_id": company, "batch_id": batch_id}},
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ],
            session=session,
        )
        .to_list(None)
    )
    return {row["_id"]: row["count"] for row in rows}


async def notify(db, key: str, company: str, phone: str, body: str, session=None) -> None:
    await collection(db, "notifications").update_one(
        {"_id": key},
        {
            "$setOnInsert": {
                "company_id": company,
                "phone": phone,
                "body": body,
                "status": "QUEUED",
                "attempts": 0,
                "created_at": now(),
            }
        },
        upsert=True,
        session=session,
    )


async def claim(db, name: str, identifier: str) -> dict | None:
    return await collection(db, name).find_one_and_update(
        {
            "_id": identifier,
            "status": {"$in": ["QUEUED", "OCR_PROCESSING", "SENDING"]},
            "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lt": now()}}],
        },
        {
            "$set": {
                "lease_until": now() + timedelta(minutes=12),
                "lease_id": uuid4().hex,
                "status": "OCR_PROCESSING" if name == "documents" else "SENDING",
            },
            "$inc": {"attempts": 1},
        },
        return_document=ReturnDocument.AFTER,
    )


def public(document: dict) -> dict:
    hidden = {"media_url", "storage_key", "lease_id", "lease_until", "phone", "company_id"}
    return {
        ("id" if key == "_id" else key): str(value) if key == "_id" else value
        for key, value in document.items()
        if key not in hidden
    }
