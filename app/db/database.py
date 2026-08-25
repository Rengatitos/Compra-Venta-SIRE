import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

logger = logging.getLogger(__name__)

MONGO_URI = settings.MONGO_URI
# sol_users, periodos y facturas viven todos en la misma base (ver README) —
# get_db() y get_user_db() son accesores separados a propósito, no una base distinta.
DB_NAME = settings.MONGO_FACTURASDB_NAME
DB_USER = DB_NAME

# Instancia global
client: AsyncIOMotorClient = None
db = None
user_db = None
vector_global_col = None
vector_users_col = None


async def connect_to_mongo():
    global client, db, user_db, vector_global_col, vector_users_col
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    user_db = client[DB_USER]
    vector_global_col = db["vector_global"]
    vector_users_col = db["vector_users"]
    logger.info(f"Connected to MongoDB.")


async def close_mongo_connection():
    global client, db, user_db, vector_global_col, vector_users_col
    if client:
        client.close()
        client = None
        db = None
        user_db = None
        vector_global_col = None
        vector_users_col = None
        logger.info("MongoDB connection closed")


def get_db():
    global db
    return db


def get_user_db():
    global user_db
    return user_db


def get_vector_global_col():
    global vector_global_col
    return vector_global_col


def get_vector_users_col():
    global vector_users_col
    return vector_users_col

