from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Automatización SUNAT API"
    API_V1_PREFIX: str = "/api/v1"

    ADMIN_TOKEN: str
    JWT_SECRET_KEY: str
    SOL_USER_CRYPTO_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 2

    MONGO_URI: str | None = None
    MONGO_FACTURASDB_NAME: str | None = None

    SUNAT_CLIENT_ID: str | None = None
    SUNAT_CLIENT_SECRET: str | None = None
    URL_SIRE_PROPUESTA: str | None = None

    GEMINI_API_KEY: str | None = None

    # Lista separada por comas. El default cubre el frontend en desarrollo.
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [origen.strip() for origen in v.split(",") if origen.strip()]
        return v


settings = Settings()
