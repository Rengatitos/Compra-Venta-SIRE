import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

client: AsyncIOMotorClient | None = None
db: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    global client, db
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_FACTURASDB_NAME]
    logger.info("Conectado a MongoDB base=%s", settings.MONGO_FACTURASDB_NAME)


async def close_mongo_connection() -> None:
    global client, db
    if client:
        client.close()
        client = None
        db = None
        logger.info("Conexión a MongoDB cerrada")


def get_db() -> AsyncIOMotorDatabase:
    return db
