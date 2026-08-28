from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.db.database import get_db
from app.repositories import empresas as repo_empresas

bearer_scheme = HTTPBearer()
api_key_header = APIKeyHeader(
    name="X-Admin-Token",
    auto_error=False,
    scheme_name="Admin Token",
    description="Token administrativo",
)


def create_token(empresa_id: str, ruc: str) -> str:
    payload = {
        "empresa_id": empresa_id,
        "ruc": ruc,
        "exp": datetime.now(UTC) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado"
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
        ) from None


def verify_admin(api_key: str = Security(api_key_header)):
    if not api_key or not settings.ADMIN_TOKEN or api_key != settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=401, detail="No autorizado o token de administrador inválido"
        )
    return api_key


async def empresa_autenticada(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db=Depends(get_db),
) -> dict:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado. Usa 'Authorization: Bearer <token>'",
        )

    payload = decode_token(credentials.credentials)
    empresa_id = payload.get("empresa_id")
    if not empresa_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido: sin empresa_id"
        )

    empresa = await repo_empresas.obtener_por_id(db, empresa_id)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Empresa no encontrada"
        )
    return empresa
