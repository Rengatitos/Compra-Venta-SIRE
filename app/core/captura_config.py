"""Configuración de captura; comparte Mongo y autenticación con SIRE."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class CapturaSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / "chatbot_whatsapp" / ".env"), extra="ignore"
    )
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: SecretStr = SecretStr("")
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_VALIDATE_SIGNATURE: bool = True
    TWILIO_WEBHOOK_URL: str = ""
    TWILIO_SINGLE_CONTENT_SID: str = ""
    TWILIO_BATCH_CONTENT_SID: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    STORAGE_PROVIDER: str = "local"
    UPLOAD_DIR: Path = ROOT / "data" / "captura"
    OCR_ENGINE: str = "rapidocr"
    OCR_LANGUAGE: str = "es"
    OCR_MODEL_PATH: str = ""
    OCR_KEYS_PATH: str = ""
    MAX_FILE_SIZE_MB: int = Field(default=20, ge=1, le=100)
    MAX_BATCH_DOCUMENTS: int = Field(default=100, ge=1, le=1000)
    MAX_PDF_PAGES: int = Field(default=30, ge=1, le=100)
    OCR_WORKER_CONCURRENCY: int = Field(default=2, ge=1, le=16)
    FRONTEND_URL: str = "http://localhost:5173"


@lru_cache
def captura_settings() -> CapturaSettings:
    return CapturaSettings()
