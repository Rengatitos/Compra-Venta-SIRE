import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.captura_config import CapturaSettings
from app.domain.captura.extraction import extract
from app.domain.captura.validation import fingerprint
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
    monkeypatch.setattr(repo, "sync_identity", AsyncMock(return_value=None))
    repo.collection(db, "documents").find_one.side_effect = lambda query, **kwargs: (
        {"_id": query["_id"]} if "lease_id" in query else None
    )

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
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    asyncio.run(pipeline.finish_batches(db))
    repo.notify.assert_not_awaited()
    batches.update_one.assert_not_awaited()


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "EXPORTED"])
@pytest.mark.parametrize("action", ["EDIT", "MOVE_PERIOD", "RESOLVE"])
def test_review_cannot_resurrect_terminal_document(monkeypatch, status, action):
    db = database()
    repo.collection(db, "documents").find_one.return_value = {
        "revision": 0,
        "status": status,
        "issues": [],
    }
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            review.mutate(db, "company", "document", 0, action, {"accounting_period": "202609"})
        )
    assert error.value.status_code == 409
    repo.collection(db, "documents").update_one.assert_not_awaited()


@pytest.mark.parametrize("status", ["PROCESSING", "READY_FOR_REVIEW", "CONFIRMED", "CANCELLED"])
def test_media_cannot_enter_closed_batch_with_stale_session(status):
    db = database()
    repo.collection(db, "batches").find_one.return_value = {
        "_id": "batch",
        "company_id": "company",
        "status": status,
        "received_count": 1,
    }
    conversation = {
        "state": "BATCH_RECEIVING",
        "phone": "+51900000000",
        "batch_id": "batch",
        "selected_period": "202609",
    }
    handler = Conversation(db, {"_id": "company"}, conversation, None)
    response = asyncio.run(handler.handle("", [{"media_url": "synthetic"}], "message"))
    assert "cerrado" in response
    repo.collection(db, "documents").insert_one.assert_not_awaited()
    repo.collection(db, "batches").update_one.assert_not_awaited()


def test_closing_batch_on_web_updates_whatsapp_session(monkeypatch):
    from app.api.v1.routes.captura import close_batch

    db = database()
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    result = asyncio.run(close_batch("batch", "company", db))
    assert result == {"status": "PROCESSING"}
    args = repo.collection(db, "sessions").update_many.call_args.args
    assert args[0] == {"company_id": "company", "batch_id": "batch"}
    assert args[1]["$set"]["state"] == "BATCH_PROCESSING"


def test_confirming_batch_on_web_releases_whatsapp_session(monkeypatch):
    from app.api.v1.routes.captura import confirm_batch

    db = database()
    repo.collection(db, "batches").find_one.return_value = {
        "_id": "batch",
        "company_id": "company",
        "status": "READY_FOR_REVIEW",
    }
    repo.collection(db, "documents").find.return_value.to_list.return_value = [
        {"_id": "document", "status": "READY"},
    ]
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    monkeypatch.setattr(repo, "batch_counts", AsyncMock(return_value={"CONFIRMED": 1}))
    result = asyncio.run(confirm_batch("batch", "company", db))
    assert "Confirmados: 1" in result["message"]
    args = repo.collection(db, "sessions").update_many.call_args.args
    assert args[0] == {"company_id": "company", "batch_id": "batch"}
    session = {"batch_id": "batch", "phone": "+51900000000", **args[1]["$set"]}
    handler = Conversation(db, {"_id": "company"}, session, None)
    assert "periodo" in asyncio.run(handler.batch())


def test_premature_web_confirmation_keeps_active_session(monkeypatch):
    from app.api.v1.routes.captura import confirm_batch

    db = database()
    repo.collection(db, "batches").find_one.return_value = {"status": "PROCESSING"}
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    with pytest.raises(HTTPException) as error:
        asyncio.run(confirm_batch("batch", "company", db))
    assert error.value.status_code == 409
    repo.collection(db, "sessions").update_many.assert_not_awaited()


def test_unrelated_edit_does_not_confirm_uncertain_ocr_date(invoice):
    extracted = extract(invoice)
    extracted.fields["document.issue_date"].confidence = 0.6
    previous = {
        "extracted": extracted.model_dump(),
        "document_date": None,
        "accounting_period": "202609",
        "period_validation": "UNVERIFIED",
        "issues": ["DATE_UNCERTAIN"],
    }
    unrelated = review.edit_changes(previous, {"fields": {"issuer.name": "Nombre corregido"}})
    assert unrelated["document_date"] is None
    assert unrelated["period_validation"] == "UNVERIFIED"
    assert "DATE_UNCERTAIN" in unrelated["issues"]
    corrected = review.edit_changes(previous, {"fields": {"document.issue_date": "2026-09-18"}})
    assert corrected["document_date"] == "2026-09-18"
    assert corrected["period_validation"] == "MATCH"
    assert "DATE_UNCERTAIN" not in corrected["issues"]


def test_identity_fields_are_reflected_in_edited_fingerprint(invoice):
    extracted = extract(invoice)
    previous = {
        "extracted": extracted.model_dump(),
        "accounting_period": "202609",
        "issues": [],
    }
    changes = review.edit_changes(previous, {"fields": {"document.number": "999999"}})
    assert changes["fingerprint"] != fingerprint(extracted)
    extracted.fields["document.number"].value = "999999"
    assert changes["fingerprint"] == fingerprint(extracted)


@pytest.mark.parametrize("status", ["RECEIVING", "CANCELLED", "READY_FOR_REVIEW"])
def test_reprocess_serializes_with_batch_completion(monkeypatch, status):
    db = database()
    repo.collection(db, "documents").find_one.return_value = {
        "revision": 0,
        "status": "FAILED",
        "batch_id": "batch",
    }
    repo.collection(db, "batches").find_one.return_value = {
        "_id": "batch",
        "status": status,
    }
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    asyncio.run(review.mutate(db, "company", "document", 0, "REPROCESS", {"status": "QUEUED"}))
    args = repo.collection(db, "batches").update_one.call_args.args
    assert args[0] == {"_id": "batch", "company_id": "company"}
    assert args[1]["$inc"] == {"revision": 1}
    if status == "READY_FOR_REVIEW":
        assert args[1]["$set"]["status"] == "PROCESSING"
    else:
        assert "$set" not in args[1]


@pytest.mark.parametrize("duplicate_source", ["identity", "file", None])
def test_edit_rechecks_duplicate_identity_and_original_file(monkeypatch, invoice, duplicate_source):
    db = database()
    extracted = extract(invoice)
    previous = {
        "_id": "document",
        "revision": 0,
        "status": "NEEDS_REVIEW",
        "extracted": extracted.model_dump(),
        "accounting_period": "202609",
        "fingerprint": fingerprint(extracted),
        "file_hash": "hash",
        "possible_duplicate": True,
        "duplicate_of": "previous_duplicate",
        "issues": ["POSSIBLE_DUPLICATE"],
    }
    repo.collection(db, "documents").find_one.side_effect = [
        previous,
        {"_id": "other_document"} if duplicate_source == "file" else None,
    ]
    synchronize = AsyncMock(
        return_value="other_document" if duplicate_source == "identity" else None
    )
    monkeypatch.setattr(repo, "sync_identity", synchronize)
    monkeypatch.setattr(repo, "transaction", transaction_stub)
    updated = asyncio.run(
        review.mutate(
            db, "company", "document", 0, "EDIT", {"fields": {"document.number": "999999"}}
        )
    )
    synchronize.assert_awaited_once_with(
        db, "company", "document", previous["fingerprint"], updated["fingerprint"], None
    )
    assert updated["possible_duplicate"] == bool(duplicate_source)
    assert updated["duplicate_of"] == ("other_document" if duplicate_source else None)
    assert ("POSSIBLE_DUPLICATE" in updated["issues"]) == bool(duplicate_source)


@pytest.mark.parametrize("link_field", ["associated_payment", "tax_document_id"])
def test_whatsapp_period_change_cannot_modify_reconciled_document(link_field):
    db = database()
    repo.collection(db, "documents").find_one.return_value = {
        "_id": "document",
        "status": "READY",
        link_field: "related-document",
    }
    session = {
        "state": "BATCH_SELECTING_PERIOD",
        "document_id": "document",
        "selected_period": "202608",
    }
    handler = Conversation(db, {"_id": "company"}, session, None)
    response = asyncio.run(handler.select_period("202609"))
    assert "conciliado" in response
    assert session["selected_period"] == "202608"
    repo.collection(db, "documents").update_one.assert_not_awaited()


@pytest.mark.parametrize("batch_id", [None, "batch"])
def test_whatsapp_cancellation_preserves_reconciled_documents_and_batch(batch_id):
    db = database()
    repo.collection(db, "documents").find_one.return_value = {
        "_id": "document",
        "status": "READY",
        "tax_document_id": "related-document",
    }
    session = {"state": "BATCH_REVIEW", "batch_id": batch_id, "document_id": "document"}
    handler = Conversation(db, {"_id": "company"}, session, None)
    response = asyncio.run(handler.cancel())
    assert "conciliado" in response
    assert session["document_id"] == "document"
    repo.collection(db, "documents").update_many.assert_not_awaited()
    repo.collection(db, "batches").update_one.assert_not_awaited()
