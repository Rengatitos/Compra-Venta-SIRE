import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.captura_config import CapturaSettings
from app.repositories import captura as repo
from app.services.captura import ingestion, pipeline, review
from app.services.captura.conversation import Conversation


async def transaction_stub(db, callback):
    return await callback(None)


def database():
    collections = {}
    db = MagicMock()

    def get_collection(name):
        if name not in collections:
            col = MagicMock()
            for method in (
                "find_one",
                "insert_one",
                "replace_one",
                "update_one",
                "update_many",
                "count_documents",
                "find_one_and_update",
            ):
                setattr(col, method, AsyncMock(return_value=None))
            col.find.return_value.to_list = AsyncMock(return_value=[])
            col.update_one.return_value = MagicMock(modified_count=1)
            collections[name] = col
        return collections[name]

    db.__getitem__.side_effect = get_collection
    return db


def test_duplicate_twilio_event_returns_saved_response_without_creating_document(monkeypatch):
    db = database()
    repo.collection(db, "events").find_one.return_value = {"response": "recibido"}
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    settings = CapturaSettings(_env_file=None, TWILIO_ACCOUNT_SID="AC" + "1" * 32)
    monkeypatch.setattr(ingestion, "captura_settings", lambda: settings)
    sid = "SM" + "2" * 32
    data = {
        "From": "whatsapp:+51900000000",
        "MessageSid": sid,
        "NumMedia": "1",
        "MediaUrl0": f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}"
        f"/Messages/{sid}/Media/ME" + "3" * 32,
        "MediaContentType0": "image/jpeg",
    }
    assert asyncio.run(ingestion.receive_webhook(db, data)) == "recibido"
    repo.collection(db, "documents").insert_one.assert_not_awaited()
    repo.collection(db, "sessions").replace_one.assert_not_awaited()


def test_unauthorized_phone_cannot_queue_documents(monkeypatch):
    db = database()
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    response = asyncio.run(
        ingestion.receive_webhook(
            db,
            {
                "From": "whatsapp:+51900000000",
                "MessageSid": "SM" + "2" * 32,
            },
        )
    )
    assert "no se encuentra autorizado" in response
    repo.collection(db, "documents").insert_one.assert_not_awaited()


def test_batch_period_selection_then_media(monkeypatch):
    db = database()
    conversation = {"state": "IDLE", "phone": "+51900000000"}
    handler = Conversation(db, {"_id": "company", "ruc": "20000000001"}, conversation, None)

    async def workflow():
        assert "periodo" in await handler.handle("LOTE", [], "first")
        await handler.handle("SEPTIEMBRE 2026", [], "second")
        batch = repo.collection(db, "batches").insert_one.call_args.args[0]
        repo.collection(db, "batches").find_one.return_value = batch
        response = await handler.handle("", [{"media_url": "synthetic"}], "third")
        return batch, response

    batch, response = asyncio.run(workflow())
    assert batch["accounting_period"] == "202609"
    assert conversation["state"] == "BATCH_RECEIVING"
    assert "Recibidos: 1" in response
    document = repo.collection(db, "documents").insert_one.call_args.args[0]
    assert document["batch_id"] == batch["_id"]
    assert document["target_period"] == "202609"
    assert document["document_date"] is None


def test_concurrent_editor_revision_is_rejected(monkeypatch):
    db = database()
    repo.collection(db, "documents").find_one.return_value = {"revision": 4, "status": "READY"}
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    with pytest.raises(HTTPException) as error:
        asyncio.run(review.mutate(db, "company", "document", 3, "CONFIRM", {"status": "CONFIRMED"}))
    assert error.value.status_code == 409
    repo.collection(db, "documents").update_one.assert_not_awaited()


def test_failed_document_does_not_block_other_49(monkeypatch, invoice):
    db = database()
    provider = MagicMock()
    provider.read.return_value = b"synthetic-image"
    monkeypatch.setattr(pipeline, "storage", lambda settings: provider)
    monkeypatch.setattr(
        pipeline, "inspect_file", lambda *args: {"mime": "image/png", "sha256": "hash"}
    )
    monkeypatch.setattr(
        pipeline,
        "extract_file_metadata",
        lambda *args: {
            "original_date": None,
            "creation_date": None,
        },
    )
    count = 0

    def recognize(*args):
        nonlocal count
        count += 1
        if count == 1:
            raise ValueError("synthetic failure")
        return invoice

    monkeypatch.setattr(pipeline, "recognize", recognize)
    monkeypatch.setattr(repo, "transaction", transaction_stub)

    async def claim(db, name, identifier):
        return {
            "_id": identifier,
            "company_id": "company",
            "storage_key": "key",
            "lease_id": identifier,
            "attempts": 1,
            "batch_id": "batch",
            "target_period": "202609",
        }

    monkeypatch.setattr(repo, "claim", claim)

    async def run():
        for index in range(50):
            repo.collection(db, "identities").find_one.return_value = {"document_id": str(index)}
            await pipeline.process_document(db, str(index))

    asyncio.run(run())
    updates = repo.collection(db, "documents").update_one.await_args_list
    statuses = [call.args[1].get("$set", {}).get("status") for call in updates]
    assert statuses.count("FAILED") == 1
    assert sum(status in {"READY", "NEEDS_REVIEW"} for status in statuses) == 49


def test_unfinished_batch_does_not_notify(monkeypatch):
    db = database()
    batches = repo.collection(db, "batches")
    batches.find.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[
            {"_id": "batch", "company_id": "company", "status": "PROCESSING"},
        ]
    )
    monkeypatch.setattr(repo, "batch_counts", AsyncMock(return_value={"READY": 49, "QUEUED": 1}))
    monkeypatch.setattr(repo, "notify", AsyncMock())
    asyncio.run(pipeline.finish_batches(db))
    repo.notify.assert_not_awaited()
    batches.update_one.assert_not_awaited()
