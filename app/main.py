import asyncio
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
from app.domain.jobs import TipoJob
from app.repositories import clasificaciones_frecuentes as repo_frecuentes
from app.repositories import codigos_vinculacion as repo_codigos_vinculacion
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import comprobantes_externos as repo_comprobantes_externos
from app.repositories import empresas as repo_empresas
from app.repositories import fichas_ruc as repo_fichas_ruc
from app.repositories import jobs as repo_jobs
from app.repositories import periodos as repo_periodos
from app.repositories import plan_cuentas as repo_plan_cuentas
from app.repositories import usuarios as repo_usuarios
from app.services.clasificador.motor import motor as motor_clasificador

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
        await repo_plan_cuentas.crear_indices(db)
        await repo_codigos_vinculacion.crear_indices(db)
        await repo_comprobantes_externos.crear_indices(db)
        await repo_fichas_ruc.crear_indices(db)
        await repo_usuarios.crear_indices(db)
        await repo_frecuentes.crear_indices(db)
    except PyMongoError:
        logger.exception("No se pudieron crear todos los índices; el servicio sigue activo")

    # Solo los de clasificación: el Mongo local lo comparte otra copia de la API
    # (la rama de WhatsApp), y marcar todos los tipos mataría sus extracciones
    # en curso cada vez que ésta se reinicia.
    try:
        huerfanos = await repo_jobs.marcar_interrumpidos(db, [TipoJob.CLASIFICACION_CUENTAS])
        if huerfanos:
            logger.warning("%s clasificaciones interrumpidas por el reinicio", huerfanos)
    except PyMongoError:
        logger.exception("No se pudieron cerrar los trabajos interrumpidos")

    # El acceso al panel falla cerrado: sin estas dos variables nadie entra. Sin
    # este aviso, el síntoma en producción sería que todo el mundo recibe 403 sin
    # ninguna pista de por qué. No se convierte en fallo de arranque porque el
    # resto del servicio (y /health) sigue siendo útil.
    if not settings.GOOGLE_CLIENT_ID:
        logger.warning("GOOGLE_CLIENT_ID no está configurado: nadie podrá iniciar sesión")
    if not settings.GOOGLE_ALLOWED_EMAILS:
        logger.warning(
            "GOOGLE_ALLOWED_EMAILS está vacía: no hay administradores fijos y solo "
            "entran los correos agregados desde el panel"
        )
    if not settings.SIRE_BOT_API_KEY:
        logger.warning("SIRE_BOT_API_KEY no está configurada: Apaclla Bot no podrá conectarse")

    # El clasificador tarda en cargar (torch, modelo de embeddings, índice):
    # se arranca en un hilo para no retrasar el arranque de la API. Quien pida
    # una clasificación antes de que termine espera a que esté listo.
    carga_clasificador = None
    if settings.CLASIFICADOR_HABILITADO:
        carga_clasificador = asyncio.create_task(asyncio.to_thread(motor_clasificador.iniciar))

    yield

    if carga_clasificador is not None and not carga_clasificador.done():
        logger.info("Apagando con el clasificador aún cargando")
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
