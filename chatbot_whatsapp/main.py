import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("chatbot_whatsapp")
TRANSACTIONS_REQUIRED = "MONGO_TRANSACTIONS_REQUIRED"
TRANSACTIONS_DETAIL = (
    "La captura requiere MongoDB con transacciones. Configura MongoDB como replica set "
    "o usa MongoDB Atlas y actualiza MONGO_URI del backend. "
    "Vuelve a intentar la operación después de corregir la conexión."
)


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
    except httpx.HTTPError as error:
        logger.error("Backend de captura no disponible: %s", type(error).__name__)
        raise HTTPException(503, "Backend no disponible; reintentar entrega") from None
    if response.status_code >= 500:
        try:
            problem = response.json()
        except ValueError:
            problem = None
        code = problem.get("code") if isinstance(problem, dict) else None
        if response.status_code == 503 and code == TRANSACTIONS_REQUIRED:
            logger.error("Backend de captura no disponible: %s. %s", code, TRANSACTIONS_DETAIL)
            return JSONResponse(
                status_code=503,
                content={"detail": TRANSACTIONS_DETAIL, "code": TRANSACTIONS_REQUIRED},
                headers={"Retry-After": "60"},
            )
        logger.error("Backend de captura no disponible: HTTP %s", response.status_code)
        raise HTTPException(503, "Backend no disponible; reintentar entrega")
    return Response(
        response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/xml"),
    )


@app.get("/health")
def health():
    return {"status": "ok"}
