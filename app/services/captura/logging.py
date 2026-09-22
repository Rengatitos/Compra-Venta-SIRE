import json
import logging

logger = logging.getLogger("sire.captura")


def log_event(event: str, **identifiers: str) -> None:
    allowed = {"request_id", "message_sid", "document_id", "batch_id", "company_id", "status"}
    logger.info(
        json.dumps(
            {"event": event, **{key: value for key, value in identifiers.items() if key in allowed}}
        )
    )
