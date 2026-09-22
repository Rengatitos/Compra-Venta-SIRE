import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure

from app.core.captura_errors import TransactionsUnavailableError
from app.main import app
from app.repositories import captura as repo


def unavailable_database(code=20):
    failure = OperationFailure(
        "Transaction numbers are only allowed on a replica set member or mongos; "
        "mongodb://private-user:private-secret@private-host/database",
        code=code,
    )
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.with_transaction = AsyncMock(side_effect=failure)
    db = MagicMock()
    db.client.start_session = AsyncMock(return_value=session)
    return db, session, failure


def test_unsupported_transaction_is_translated_without_nontransactional_fallback():
    db, session, _ = unavailable_database()
    callback = AsyncMock()
    with pytest.raises(TransactionsUnavailableError) as error:
        asyncio.run(repo.transaction(db, callback))
    assert "replica set" in str(error.value)
    assert "MONGO_URI" in str(error.value)
    assert "private-secret" not in str(error.value)
    session.with_transaction.assert_awaited_once_with(callback)
    callback.assert_not_awaited()


def test_other_mongo_errors_are_not_misreported_as_missing_transactions():
    db, _, failure = unavailable_database(code=13)
    with pytest.raises(OperationFailure) as error:
        asyncio.run(repo.transaction(db, AsyncMock()))
    assert error.value is failure


@pytest.mark.parametrize("operation", ["phones", "whatsapp"])
def test_capture_api_returns_actionable_503_without_connection_details(
    monkeypatch, caplog, operation
):
    from app.api.v1.routes import captura as routes
    from app.db.database import get_db

    db, _, _ = unavailable_database()
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: db)
    monkeypatch.setitem(app.dependency_overrides, routes.company_id, lambda: "company")
    monkeypatch.setattr(
        routes,
        "validate_webhook",
        AsyncMock(return_value={"From": "whatsapp:+51900000000", "MessageSid": "SM" + "1" * 32}),
    )
    with caplog.at_level(logging.ERROR):
        client = TestClient(app)
        if operation == "phones":
            response = client.post("/api/v1/captura/phones", json={"phone": "+51900000000"})
        else:
            response = client.post("/api/v1/captura/whatsapp", data={"Body": "HOLA"})
    assert response.status_code == 503
    assert response.json() == {
        "detail": TransactionsUnavailableError.detail,
        "code": TransactionsUnavailableError.code,
    }
    assert response.headers["Retry-After"] == "60"
    assert TransactionsUnavailableError.code in caplog.text
    assert "private-secret" not in response.text + caplog.text
    assert "private-host" not in response.text + caplog.text


def test_whatsapp_proxy_preserves_known_unavailability_without_leaking_backend_text(
    monkeypatch, caplog
):
    from chatbot_whatsapp import main as proxy

    backend = AsyncMock()
    backend.post.return_value = httpx.Response(
        503,
        json={"code": TransactionsUnavailableError.code, "detail": "private-secret"},
    )
    monkeypatch.setattr(proxy.app.state, "client", backend, raising=False)
    with caplog.at_level(logging.ERROR):
        response = TestClient(proxy.app).post("/webhooks/twilio/whatsapp", data={"Body": "HOLA"})
    assert response.status_code == 503
    assert response.json() == {
        "detail": TransactionsUnavailableError.detail,
        "code": TransactionsUnavailableError.code,
    }
    assert TransactionsUnavailableError.code in caplog.text
    assert "private-secret" not in response.text + caplog.text


@pytest.mark.parametrize("failure", ["http", "transport"])
def test_whatsapp_proxy_sanitizes_unknown_backend_failures(monkeypatch, caplog, failure):
    from chatbot_whatsapp import main as proxy

    backend = AsyncMock()
    if failure == "http":
        backend.post.return_value = httpx.Response(500, text="private-secret driver traceback")
    else:
        backend.post.side_effect = httpx.ConnectError("private-secret connection URL")
    monkeypatch.setattr(proxy.app.state, "client", backend, raising=False)
    with caplog.at_level(logging.ERROR):
        response = TestClient(proxy.app).post("/webhooks/twilio/whatsapp", data={"Body": "HOLA"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Backend no disponible; reintentar entrega"
    assert "private-secret" not in response.text + caplog.text
