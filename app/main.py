from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.routes import analysis, analytics, invoices, periods, references, sire, sol_users
from app.db.database import (
    close_mongo_connection,
    connect_to_mongo,
    get_db,
    get_vector_global_col,
    get_vector_users_col,
)
from app.core.config import settings
from app.services import analisis_ia, maintenance


log_dir = Path(__file__).resolve().parents[1] / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "automat_api.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
    force=True,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Desplegando API de facturas...")
    await connect_to_mongo()
    db = get_db()

    try:
        eliminadas = await maintenance.deduplicate_facturas(db)
        if eliminadas:
            logger.warning("Facturas duplicadas eliminadas=%s", eliminadas)
    except PyMongoError as exc:
        logger.exception("No se pudo ejecutar deduplicacion de facturas: %s", exc)

    await db["sol_users"].create_index("ruc")
    await db["periodos"].create_index([("user_id", 1), ("periodo", 1)], unique=True)
    await db["facturas"].create_index([("user_id", 1), ("periodo", 1)])
    await db["facturas"].create_index("serie_numero")
    try:
        await db["facturas"].create_index(
            [("user_id", 1), ("periodo", 1), ("serie_numero", 1)],
            unique=True,
            partialFilterExpression={"serie_numero": {"$gt": ""}},
            name="uniq_facturas_user_periodo_serie",
        )
    except (DuplicateKeyError, OperationFailure) as exc:
        logger.warning(
            "No se pudo crear indice unico de facturas (servicio sigue activo): %s",
            exc,
        )
    except PyMongoError as exc:
        logger.exception(
            "Error inesperado creando indice unico de facturas (servicio sigue activo): %s",
            exc,
        )

    vector_global = get_vector_global_col()
    vector_users = get_vector_users_col()
    await vector_global.create_index([("metadata.documento", 1)])
    await vector_users.create_index([("user_id", 1), ("metadata.documento", 1)])

    await analisis_ia.cargar_vector(vector_global)

    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API para orquestar los scripts de automatizacion de SUNAT",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sol_users.router, prefix="/sol-users", tags=["SOL Users"])
app.include_router(
    periods.router,
    prefix="/sol-users/{user_id}/periodos",
    tags=["Periods"],
)
app.include_router(
    sire.router,
    prefix="/sol-users/{user_id}/periodos/{periodo}/propuesta",
    tags=["SIRE"],
)
app.include_router(
    analysis.router,
    prefix="/sol-users/{user_id}/periodos/{periodo}/analisis",
    tags=["Analysis"],
)
app.include_router(
    references.router,
    prefix="/references",
    tags=["References"],
)
app.include_router(
    invoices.router,
    prefix="/sol-users/{user_id}/periodos/{periodo}/facturas",
    tags=["Invoices"],
)
app.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["Analytics"],
)


@app.get("/")
def root():
    return {
        "mensaje": "Bienvenido a la API de Automatizacion SUNAT."
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
