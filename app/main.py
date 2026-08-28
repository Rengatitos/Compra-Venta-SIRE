import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.database import close_mongo_connection, connect_to_mongo, get_db
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import empresas as repo_empresas
from app.repositories import jobs as repo_jobs
from app.repositories import periodos as repo_periodos
from app.repositories import vectores as repo_vectores
from app.services import analisis_ia

log_dir = Path(__file__).resolve().parents[1] / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / "automat_api.log", encoding="utf-8"),
    ],
    force=True,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando la API de automatización SUNAT")
    await connect_to_mongo()
    db = get_db()

    try:
        await repo_empresas.crear_indices(db)
        await repo_periodos.crear_indices(db)
        await repo_comprobantes.crear_indices(db)
        await repo_jobs.crear_indices(db)
        await repo_vectores.crear_indices(db)
    except PyMongoError:
        logger.exception("No se pudieron crear todos los índices; el servicio sigue activo")

    await analisis_ia.cargar_vector(db)

    yield

    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API para orquestar la automatización del SIRE de SUNAT",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["Sistema"])
def health_check():
    return {"status": "ok"}
