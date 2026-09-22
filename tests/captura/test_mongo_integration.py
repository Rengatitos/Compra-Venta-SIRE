"""Pruebas reales contra un replica set local desechable; nunca usan MONGO_URI."""

import asyncio
import io
import os
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image

from app.api.v1.routes import captura as routes
from app.core.auth import empresa_autenticada
from app.core.captura_config import CapturaSettings
from app.db.database import get_db
from app.domain.captura.models import OCRBlock, OCRResult
from app.repositories import captura as repo
from app.repositories import empresas
from app.services.captura import conversation, ingestion, pipeline

URI = os.environ.get("CAPTURA_TEST_MONGO_URI")
pytestmark = pytest.mark.skipif(
    not URI, reason="Requiere CAPTURA_TEST_MONGO_URI (replica set local)"
)


def test_real_mongo_webhook_batch_review_and_tenant_isolation(monkeypatch, tmp_path):
    from twilio.request_validator import RequestValidator

    assert URI.startswith("mongodb://127.0.0.1:27019/")
    settings = CapturaSettings(
        _env_file=None,
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_AUTH_TOKEN="synthetic-secret",
        TWILIO_PHONE_NUMBER="+15000000000",
        TWILIO_WEBHOOK_URL="https://example.test/webhooks/twilio/whatsapp",
        UPLOAD_DIR=tmp_path,
    )
    for module in (routes, ingestion, conversation, pipeline):
        monkeypatch.setattr(module, "captura_settings", lambda: settings)

    async def media(url, config):
        index = int(url.split("/Messages/SM")[1][:32])
        stream = io.BytesIO()
        Image.new("RGB", (64, 64), (index, 0, 0)).save(stream, format="PNG")
        return stream.getvalue()

    def ocr(content, mime):
        with Image.open(io.BytesIO(content)) as image:
            index = image.getpixel((0, 0))[0]
        month = "10" if index == 5 else "09"
        return OCRResult(
            blocks=[
                OCRBlock(text=line, confidence=0.99)
                for line in [
                    "FACTURA ELECTRONICA",
                    f"F001-0000000{index}",
                    "RUC: 20000000001",
                    f"Fecha: 18/{month}/2026",
                    "Subtotal: S/ 100.00",
                    "IGV: S/ 18.00",
                    "Total: S/ 118.00",
                ]
            ]
        )

    monkeypatch.setattr(pipeline, "download_media", media)
    monkeypatch.setattr(pipeline, "recognize", ocr)

    async def run():
        client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
        db_name = "captura_test_" + uuid4().hex
        db = client[db_name]
        try:
            await repo.crear_indices(db)
            company = await empresas.crear(db, {"ruc": "20000000001", "usuario": "SINTETICO"})
            other = await empresas.crear(db, {"ruc": "20000000010", "usuario": "SINTETICO2"})
            current_company = company
            app = FastAPI()
            app.include_router(routes.router)
            app.dependency_overrides[get_db] = lambda: db
            app.dependency_overrides[empresa_autenticada] = lambda: current_company
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http:
                authorized = await http.post("/captura/phones", json={"phone": "+51900000000"})
                assert authorized.status_code == 200, authorized.text

                async def webhook(index, body="", has_media=False):
                    sid = f"SM{index:032d}"
                    data = {
                        "AccountSid": settings.TWILIO_ACCOUNT_SID,
                        "MessageSid": sid,
                        "From": "whatsapp:+51900000000",
                        "To": "whatsapp:+15000000000",
                        "Body": body,
                        "NumMedia": "1" if has_media else "0",
                    }
                    if has_media:
                        data.update(
                            MediaContentType0="image/png",
                            MediaUrl0=(
                                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}"
                                f"/Messages/{sid}/Media/ME" + "3" * 32
                            ),
                        )
                    signature = RequestValidator("synthetic-secret").compute_signature(
                        settings.TWILIO_WEBHOOK_URL, data
                    )
                    response = await http.post(
                        "/captura/whatsapp", data=data, headers={"X-Twilio-Signature": signature}
                    )
                    assert response.status_code == 200, response.text
                    return response

                await webhook(1, "LOTE")
                await webhook(2, "SEPTIEMBRE 2026")
                await asyncio.gather(webhook(3, has_media=True), webhook(3, has_media=True))
                await webhook(4, has_media=True)
                await webhook(5, has_media=True)
                assert await repo.collection(db, "documents").count_documents({}) == 3
                batch = await repo.collection(db, "batches").find_one({})
                assert batch["received_count"] == 3
                await webhook(6, "FIN")
                docs = await repo.collection(db, "documents").find().to_list(None)
                for doc in docs:
                    await pipeline.process_document(db, doc["_id"])
                await pipeline.finish_batches(db)
                counts = await repo.batch_counts(db, str(company["_id"]), batch["_id"])
                assert counts == {"READY": 2, "NEEDS_REVIEW": 1}, counts
                assert await repo.collection(db, "notifications").count_documents({}) == 1
                listing = await http.get("/captura/documents", params={"period": "202609"})
                assert listing.json()["total"] == 3
                outside = next(
                    row for row in listing.json()["items"] if row["status"] == "NEEDS_REVIEW"
                )
                assert outside["period_validation"] == "MISMATCH"
                rejected = await http.post(
                    f"/captura/documents/{outside['id']}/confirm",
                    json={"revision": outside["revision"]},
                )
                assert rejected.status_code == 409
                moved = await http.post(
                    f"/captura/documents/{outside['id']}/move-period",
                    json={
                        "revision": outside["revision"],
                        "accounting_period": "202610",
                        "note": "Fecha verificada",
                    },
                )
                assert moved.status_code == 200, moved.text
                assert moved.json()["status"] == "READY"
                confirmed = await http.post(
                    f"/captura/documents/{outside['id']}/confirm",
                    json={"revision": moved.json()["revision"]},
                )
                assert confirmed.status_code == 200
                history = await http.get(f"/captura/documents/{outside['id']}")
                assert any(item["action"] == "MOVE_PERIOD" for item in history.json()["audit"])
                current_company = other
                denied = await http.get(f"/captura/documents/{outside['id']}/file")
                assert denied.status_code == 404
                assert (await http.get("/captura/documents")).json()["total"] == 0
        finally:
            assert db_name.startswith("captura_test_")
            await client.drop_database(db_name)
            client.close()

    asyncio.run(run())
