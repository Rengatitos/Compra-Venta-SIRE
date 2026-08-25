from datetime import datetime, timedelta, timezone

import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.db.database import get_user_db

bearer_scheme = HTTPBearer()
api_key_header = APIKeyHeader(
    name="X-Admin-Token",
    auto_error=False,
    scheme_name="Admin Token",
    description="admin token",
)


def create_token(user_id: str, ruc: str) -> str:
    payload = {
        "user_id": user_id,
        "ruc": ruc,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


def verify_admin(api_key: str = Security(api_key_header)):
    if not api_key or not settings.ADMIN_TOKEN or api_key != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado o token de administrador inválido")
    return api_key


async def verify_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db=Depends(get_user_db),
) -> dict:
    """Decodifica el JWT y devuelve el documento del usuario desde MongoDB."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado. Usa 'Authorization: Bearer <token>'",
        )
    payload = decode_token(credentials.credentials)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido: sin user_id")

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_id inválido en token")

    user = await db["sol_users"].find_one({"_id": oid})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    return user


def require_same_user(user_id: str, user: dict = Depends(verify_user)) -> dict:
    """Dependencia compartida: exige que el usuario autenticado sea el dueño del `user_id` del path.

    Reemplaza el bloque `if str(user["_id"]) != user_id: raise HTTPException(403, ...)`
    que estaba duplicado en periods.py, invoices.py, sol_users.py y analysis.py.
    """
    if str(user["_id"]) != user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a este recurso")
    return user
