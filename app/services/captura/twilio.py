import json
import re
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Request

from app.core.captura_config import CapturaSettings


def normalize_phone(value: str) -> str:
    value = value.removeprefix("whatsapp:").strip()
    if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
        raise ValueError("Usa un teléfono internacional, por ejemplo +519XXXXXXXX")
    return value


async def validate_webhook(request: Request, settings: CapturaSettings) -> dict:
    from twilio.request_validator import RequestValidator

    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Se requiere formulario URL encoded")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(413, "Webhook demasiado grande")
    from urllib.parse import parse_qsl

    from starlette.datastructures import FormData

    form = FormData(parse_qsl(body.decode(), keep_blank_values=True, max_num_fields=100))
    if settings.TWILIO_VALIDATE_SIGNATURE:
        secret = settings.TWILIO_AUTH_TOKEN.get_secret_value()
        if not secret or not settings.TWILIO_WEBHOOK_URL:
            raise HTTPException(503, "Twilio no está configurado")
        if not RequestValidator(secret).validate(
            settings.TWILIO_WEBHOOK_URL, form, request.headers.get("X-Twilio-Signature", "")
        ):
            raise HTTPException(403, "Firma inválida")
    data = dict(form)
    if data.get("AccountSid") != settings.TWILIO_ACCOUNT_SID:
        raise HTTPException(403, "Cuenta inválida")
    if data.get("To") != "whatsapp:" + settings.TWILIO_PHONE_NUMBER.removeprefix("whatsapp:"):
        raise HTTPException(403, "Destino inválido")
    if not re.fullmatch(r"(?:SM|MM)[a-fA-F0-9]{32}", data.get("MessageSid", "")):
        raise HTTPException(422, "MessageSid inválido")
    return data


def validate_media_url(url: str, settings: CapturaSettings) -> None:
    parsed = urlparse(url)
    path = rf"/2010-04-01/Accounts/{re.escape(settings.TWILIO_ACCOUNT_SID)}/Messages/"
    path += r"(?:SM|MM)[a-fA-F0-9]{32}/Media/ME[a-fA-F0-9]{32}"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.twilio.com"
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(path, parsed.path)
    ):
        raise ValueError("URL multimedia no permitida")


async def download_media(url: str, settings: CapturaSettings) -> bytes:
    validate_media_url(url, settings)
    auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN.get_secret_value())
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        # Twilio redirige a su CDN firmada. Nunca reenviar Basic Auth al CDN.
        async with client.stream("GET", url, auth=auth) as response:
            if response.is_redirect:
                location = response.headers.get("location", "")
                host = urlparse(location)
                if (
                    host.scheme != "https"
                    or not (host.hostname or "").endswith(".twiliocdn.com")
                    or host.port not in (None, 443)
                    or host.username
                    or host.password
                ):
                    raise ValueError("Redirección multimedia no permitida")
                url, auth = location, None
            else:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                        raise ValueError("Archivo demasiado grande")
                return bytes(content)
        async with client.stream("GET", url, auth=auth) as stream:
            stream.raise_for_status()
            content = bytearray()
            async for chunk in stream.aiter_bytes():
                content.extend(chunk)
                if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                    raise ValueError("Archivo demasiado grande")
            return bytes(content)


async def send_message(phone: str, body: str, settings: CapturaSettings, kind: str = "") -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        data = {
            "From": "whatsapp:" + settings.TWILIO_PHONE_NUMBER.removeprefix("whatsapp:"),
            "To": "whatsapp:" + phone,
            "Body": body[:1500],
        }
        template = (
            settings.TWILIO_BATCH_CONTENT_SID
            if kind == "batch"
            else settings.TWILIO_SINGLE_CONTENT_SID
            if kind == "document"
            else ""
        )
        endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN.get_secret_value())
        if template:
            interactive = {key: value for key, value in data.items() if key != "Body"}
            interactive.update(ContentSid=template, ContentVariables=json.dumps({"1": body[:1000]}))
            response = await client.post(endpoint, auth=auth, data=interactive)
            if response.is_success:
                return response.json()["sid"]
            # Un error de elegibilidad/plantilla usa la respuesta textual.
            # Los errores de transporte se reintentan por el outbox, no duplican envíos aquí.
            if response.status_code not in {400, 422}:
                response.raise_for_status()
        response = await client.post(
            endpoint,
            auth=auth,
            data=data,
        )
        response.raise_for_status()
        return response.json()["sid"]
