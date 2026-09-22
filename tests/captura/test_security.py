import asyncio
import io
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.captura_config import CapturaSettings
from app.services.captura.review import require_document
from app.services.captura.storage import LocalStorage, inspect_file
from app.services.captura.twilio import normalize_phone, validate_media_url, validate_webhook


def test_storage_traversal_and_file_validation(tmp_path):
    provider = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        provider.read("../secret")
    from PIL import UnidentifiedImageError

    with pytest.raises(UnidentifiedImageError):
        inspect_file(b"<script>not an image</script>", CapturaSettings(_env_file=None))
    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    content = stream.getvalue()
    key = provider.put(content)
    assert provider.read(key) == content
    assert inspect_file(content, CapturaSettings(_env_file=None))["mime"] == "image/png"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/internal",
        "https://api.twilio.com.evil.test/a",
        "https://api.twilio.com@evil.test/a",
        "file:///etc/passwd",
    ],
)
def test_media_ssrf_rejected(url):
    with pytest.raises(ValueError):
        validate_media_url(url, CapturaSettings(_env_file=None))


def test_phone_normalization():
    assert normalize_phone("whatsapp:+51900000000") == "+51900000000"
    with pytest.raises(ValueError):
        normalize_phone("900000000")


def test_document_lookup_always_scopes_company():
    db = MagicMock()
    db.__getitem__.return_value.find_one = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as error:
        asyncio.run(require_document(db, "company-A", "document-B"))
    assert error.value.status_code == 404
    assert db.__getitem__.return_value.find_one.call_args.args[0] == {
        "_id": "document-B",
        "company_id": "company-A",
    }


def test_signature_uses_public_url_and_all_parameters():
    from twilio.request_validator import RequestValidator

    settings = CapturaSettings(
        _env_file=None,
        TWILIO_ACCOUNT_SID="AC" + "1" * 32,
        TWILIO_AUTH_TOKEN="synthetic-secret",
        TWILIO_PHONE_NUMBER="+15000000000",
        TWILIO_WEBHOOK_URL="https://example.test/webhooks/twilio/whatsapp",
    )
    fields = {
        "AccountSid": settings.TWILIO_ACCOUNT_SID,
        "MessageSid": "SM" + "2" * 32,
        "From": "whatsapp:+51900000000",
        "To": "whatsapp:+15000000000",
        "Body": "AYUDA",
        "NumMedia": "0",
        "FutureParameter": "retained",
    }
    signature = RequestValidator("synthetic-secret").compute_signature(
        settings.TWILIO_WEBHOOK_URL, fields
    )

    def request(sig):
        async def receive():
            return {"type": "http.request", "body": urlencode(fields).encode(), "more_body": False}

        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/captura/whatsapp",
                "headers": [
                    (b"content-type", b"application/x-www-form-urlencoded"),
                    (b"x-twilio-signature", sig.encode()),
                ],
            },
            receive,
        )

    assert asyncio.run(validate_webhook(request(signature), settings))["Body"] == "AYUDA"
    with pytest.raises(HTTPException) as error:
        asyncio.run(validate_webhook(request("invalid"), settings))
    assert error.value.status_code == 403
