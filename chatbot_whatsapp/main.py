from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).with_name(".env"), extra="ignore")
    API_BASE_URL: str = "http://127.0.0.1:9007/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        app.state.client = client
        yield


app = FastAPI(title="Cliente WhatsApp SIRE", lifespan=lifespan)
settings = Settings()


@app.post("/webhooks/twilio/whatsapp")
async def webhook(request: Request):
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Formato no permitido")
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 65536:
            raise HTTPException(413, "Webhook demasiado grande")
    try:
        response = await request.app.state.client.post(
            settings.API_BASE_URL.rstrip("/") + "/captura/whatsapp",
            content=bytes(content),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": request.headers.get("X-Twilio-Signature", ""),
            },
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Backend no disponible; reintentar entrega") from None
    return Response(
        response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/xml"),
    )


@app.get("/health")
def health():
    return {"status": "ok"}
