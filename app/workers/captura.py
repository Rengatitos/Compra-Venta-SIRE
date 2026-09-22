import asyncio
from datetime import timedelta

from celery import Celery
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.captura_config import captura_settings
from app.core.config import settings
from app.repositories import captura as repo
from app.services.captura.pipeline import deliver_notification, finish_batches, process_document

celery = Celery("captura", broker=captura_settings().REDIS_URL)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=600,
    task_soft_time_limit=570,
    worker_concurrency=captura_settings().OCR_WORKER_CONCURRENCY,
    broker_transport_options={"visibility_timeout": 900},
    beat_schedule={"recover-capture": {"task": "captura.dispatch", "schedule": 5.0}},
)


async def with_database(operation, *args):
    client = AsyncIOMotorClient(settings.MONGO_URI)
    try:
        return await operation(client[settings.MONGO_FACTURASDB_NAME], *args)
    finally:
        client.close()


@celery.task(name="captura.document")
def document_task(identifier: str):
    asyncio.run(with_database(process_document, identifier))


@celery.task(name="captura.notification")
def notification_task(identifier: str):
    asyncio.run(with_database(deliver_notification, identifier))


async def dispatch(db):
    # Mongo es el outbox durable: una caída de Redis no pierde documentos aceptados.
    for name, task in (("documents", document_task), ("notifications", notification_task)):
        cursor = (
            repo.collection(db, name)
            .find(
                {
                    "status": {"$in": ["QUEUED", "OCR_PROCESSING", "SENDING"]},
                    "$or": [
                        {"lease_until": {"$exists": False}},
                        {"lease_until": {"$lt": repo.now()}},
                    ],
                }
            )
            .limit(100)
        )
        async for item in cursor:
            reserved = await repo.collection(db, name).update_one(
                {
                    "_id": item["_id"],
                    "$or": [
                        {"dispatch_until": {"$exists": False}},
                        {"dispatch_until": {"$lt": repo.now()}},
                    ],
                },
                {"$set": {"dispatch_until": repo.now() + timedelta(minutes=2)}},
            )
            if reserved.modified_count:
                try:
                    task.delay(item["_id"])
                except Exception:
                    await repo.collection(db, name).update_one(
                        {"_id": item["_id"]}, {"$unset": {"dispatch_until": ""}}
                    )
                    raise
    await finish_batches(db)


@celery.task(name="captura.dispatch")
def dispatch_task():
    asyncio.run(with_database(dispatch))
