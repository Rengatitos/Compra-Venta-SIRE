from datetime import timedelta

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.captura_config import captura_settings
from app.repositories import captura as repo
from app.repositories import empresas
from app.services.captura.conversation import Conversation
from app.services.captura.twilio import normalize_phone, validate_media_url


async def receive_webhook(db, data: dict) -> str:
    settings = captura_settings()
    try:
        phone = normalize_phone(data.get("From", ""))
        count = int(data.get("NumMedia", "0"))
        if not 0 <= count <= 10:
            raise ValueError("Cantidad multimedia inválida")
        media = []
        for index in range(count):
            url = data.get(f"MediaUrl{index}", "")
            validate_media_url(url, settings)
            mime = data.get(f"MediaContentType{index}", "")
            if mime not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
                return "Envía una imagen JPG/PNG/WebP o un PDF."
            media.append({"media_url": url, "declared_mime": mime})
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    sid = data["MessageSid"]

    async def apply(tx):
        existing = await repo.collection(db, "events").find_one({"_id": sid}, session=tx)
        if existing:
            return existing["response"]
        authorization = await repo.collection(db, "phones").find_one(
            {"phone": phone, "active": True}, session=tx
        )
        if not authorization:
            return "⚠️ Este número no se encuentra autorizado para registrar comprobantes."
        company = await empresas.obtener_por_id(db, authorization["company_id"])
        if not company or company.get("activo") is False:
            return "⚠️ La empresa no está activa."
        company_id = str(company["_id"])
        session_id = company_id + ":" + phone
        conversation = await repo.collection(db, "sessions").find_one(
            {"_id": session_id}, session=tx
        )
        timestamp = repo.now()
        if not conversation:
            conversation = {
                "_id": session_id,
                "company_id": company_id,
                "phone": phone,
                "state": "IDLE",
                "created_at": timestamp,
            }
        # No perder referencias a lotes/documentos pendientes cuando expire la sesión.
        if (
            conversation.get("expires_at")
            and conversation["expires_at"].replace(tzinfo=timestamp.tzinfo) < timestamp
            and not conversation.get("batch_id")
            and not conversation.get("document_id")
        ):
            conversation.update(state="IDLE", selected_period=None)
        # Límite por remitente, persistente y compartido entre réplicas.
        minute = timestamp.strftime("%Y%m%d%H%M")
        requests = (
            conversation.get("minute_count", 0) if conversation.get("minute") == minute else 0
        )
        if requests >= 90:
            return "Recibimos muchos mensajes. Espera un minuto antes de continuar."
        conversation.update(minute=minute, minute_count=requests + 1)
        response = await Conversation(db, company, conversation, tx).handle(
            data.get("ButtonPayload") or data.get("Body", ""), media, sid
        )
        conversation.update(updated_at=timestamp, expires_at=timestamp + timedelta(hours=24))
        await repo.collection(db, "sessions").replace_one(
            {"_id": session_id}, conversation, upsert=True, session=tx
        )
        await repo.collection(db, "events").insert_one(
            {
                "_id": sid,
                "message_sid": sid,
                "company_id": company_id,
                "received_at": timestamp,
                "media_count": count,
                "response": response,
            },
            session=tx,
        )
        return response

    try:
        return await repo.transaction(db, apply)
    except DuplicateKeyError:
        event = await repo.collection(db, "events").find_one({"_id": sid})
        if event:
            return event["response"]
        # Creación concurrente de sesión: repetir con la sesión ya persistida.
        return await repo.transaction(db, apply)
