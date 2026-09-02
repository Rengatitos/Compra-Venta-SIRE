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
    # Un endpoint por libro. `URL_SIRE_PROPUESTA` conserva su nombre —sin
    # sufijo— para no romper los despliegues que ya la tienen puesta.
    URL_SIRE_PROPUESTA: str | None = None
    URL_SIRE_PROPUESTA_VENTAS: str | None = None

    # Paginación de la propuesta. Antes `page=1&perPage=100` iba incrustado y
    # cualquier periodo con más de cien comprobantes se truncaba en silencio;
    # en ventas, con las boletas, eso pasa casi siempre. `SIRE_MAX_PAGINAS` es
    # el freno por si el endpoint ignora `page` y devuelve siempre lo mismo.
    # 100 es además el techo que acepta el SIRE: por encima responde 422.
    SIRE_PER_PAGE: int = 100
    SIRE_MAX_PAGINAS: int = 50

    # Scraping del portal SOL. Hasta ahora todos estos valores estaban
    # incrustados en el código, así que ajustar el scraper obligaba a tocarlo.
    SUNAT_SCRAPER_HEADLESS: bool = True
    # Techo de espera de cada paso de Playwright. Subirlo sólo si SUNAT va
    # lento: multiplica el coste de cada comprobante que falla.
    SUNAT_SCRAPER_TIMEOUT_MS: int = 15000
    # Techo aparte para decidir que SUNAT no tiene el comprobante. Cuando sí
    # lo tiene, el enlace aparece en menos de un segundo, así que esperar el
    # timeout general sólo alargaba los que faltan.
    SUNAT_TIMEOUT_BUSQUEDA_MS: int = 8000
    # Comprobantes que se piden como máximo en una extracción. Antes era un
    # `limit=100` escondido en el repositorio que recortaba el trabajo sin
    # decir nada.
    SUNAT_MAX_COMPROBANTES: int = 100

    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_CHAT_MODEL: str = "gemma3:4b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    RAG_TOP_K_RULES: int = 6
    RAG_TOP_K_ACCOUNTS: int = 8
    RAG_TOP_K_HISTORICAL: int = 6
    RAG_CONFIDENCE_THRESHOLD: float = 0.80

    # API externa que traduce comprobantes, documentos y glosas a los códigos
    # que espera la plantilla de Contasis.
    RAG_MAX_CONCURRENCY: int = 5
    # Acceso a Gemini. Hay dos modos excluyentes:
    #   - API de AI Studio: basta GEMINI_API_KEY.
    #   - Vertex AI: define VERTEX_PROJECT (y opcionalmente el JSON de la
    #     service account). Tiene la cuota del proyecto de Google Cloud en vez
    #     del saldo prepagado de AI Studio, que es lo que se agotó.
    # Si VERTEX_PROJECT está definido, Vertex gana.
    GEMINI_API_KEY: str | None = None
    VERTEX_PROJECT: str | None = None
    # `global` es la única región que sirve a la vez gemini-3.6-flash y
    # gemini-embedding-001: en us-central1 el modelo de texto da 404.
    VERTEX_LOCATION: str = "global"
    # Ruta al JSON de la service account. Si se deja vacío se usan las
    # credenciales por defecto del entorno (ADC).
    VERTEX_CREDENTIALS_FILE: str | None = None

    # Segundos mínimos entre llamadas a Gemini. El tier gratuito de AI Studio
    # admitía 5 req/min, de ahí los 13s; en Vertex la cuota es mucho mayor y
    # dejarlo así sólo alarga los lotes (60 comprobantes = 13 minutos de espera
    # pura), así que es configurable por entorno.
    GEMINI_MIN_INTERVAL_SECONDS: float = 13.0

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
