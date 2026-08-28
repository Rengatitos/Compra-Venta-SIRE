import json
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# El default cubre el frontend en desarrollo (Vite en 5173).
CORS_ORIGINS_POR_DEFECTO = ["http://localhost:5173", "http://localhost:3000"]


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

    # Orígenes permitidos por CORS. Se acepta tanto la lista separada por comas
    # que documenta `.env.example` como una lista JSON.
    #
    # `NoDecode` es imprescindible: sin él, pydantic-settings trata cualquier
    # campo complejo del entorno como JSON y falla en `prepare_field_value`
    # antes de que `_parsear_origenes` llegue a ejecutarse, así que el formato
    # con comas reventaba el arranque con JSONDecodeError.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = CORS_ORIGINS_POR_DEFECTO

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parsear_origenes(cls, v):
        if not isinstance(v, str):
            return v

        texto = v.strip()
        # Un valor vacío significa "no lo configuré", no "no permitas nada":
        # dejar la lista vacía bloquearía al frontend sin ninguna pista del por qué.
        if not texto:
            return list(CORS_ORIGINS_POR_DEFECTO)

        # Con NoDecode ya nadie decodifica el JSON, así que hay que hacerlo aquí
        # para no romper los despliegues que ya usaban esa forma.
        if texto.startswith("["):
            try:
                decodificado = json.loads(texto)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "CORS_ORIGINS parece una lista JSON pero no se pudo decodificar. "
                    "Usa una lista separada por comas o un JSON válido."
                ) from exc
            if not isinstance(decodificado, list):
                raise ValueError("CORS_ORIGINS en JSON debe ser una lista de cadenas")
            return [str(origen).strip() for origen in decodificado if str(origen).strip()]

        return [origen.strip() for origen in texto.split(",") if origen.strip()]


settings = Settings()
