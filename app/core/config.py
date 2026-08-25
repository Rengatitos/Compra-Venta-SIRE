from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Automatización SUNAT API"

    ADMIN_TOKEN: str
    JWT_SECRET_KEY: str
    SOL_USER_CRYPTO_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 2

    MONGO_URI: Optional[str] = None
    MONGO_FACTURASDB_NAME: Optional[str] = None

    SUNAT_CLIENT_ID: Optional[str] = None
    SUNAT_CLIENT_SECRET: Optional[str] = None
    URL_SIRE_PROPUESTA: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
