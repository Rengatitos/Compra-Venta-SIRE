"""Shared authentication utilities for microservices."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

try:
    import jwt as pyjwt
    JWT_BACKEND = "pyjwt"
except ImportError:
    pyjwt = None
    try:
        JWT_BACKEND = "python-jose"
        from jose import JWTError as JoseJWTError
        from jose import ExpiredSignatureError as JoseExpiredSignatureError
        from jose import jwt as jose_jwt
    except ImportError:
        JWT_BACKEND = "none"
        JoseJWTError = Exception
        JoseExpiredSignatureError = Exception
        jose_jwt = None


class TokenPayload(BaseModel):
    """Token payload for other microservices."""

    sub: str  # user_id
    email: str
    first_name: str
    last_name: str
    role: str
    permissions: list[str]
    iss: str
    aud: str
    exp: int
    iat: int
    empresa_id: Optional[str] = None
    representante_id: Optional[str] = None


# Configuration
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
AUTH_API_ISSUER = "auth-api"
INTERNAL_APIS_AUDIENCE = "internal-apis"


class AuthError(HTTPException):
    """Custom authentication error."""

    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


security = HTTPBearer()


def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenPayload:
    """Verify JWT token from Authorization header."""
    token = credentials.credentials

    try:
        if JWT_BACKEND == "pyjwt":
            payload = pyjwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_ALGORITHM],
                audience=INTERNAL_APIS_AUDIENCE,
                issuer=AUTH_API_ISSUER,
            )
        else:
            if JWT_BACKEND == "none" or jose_jwt is None:
                raise AuthError("No hay backend JWT instalado en este entorno")
            payload = jose_jwt.decode(
                token,
                JWT_SECRET_KEY,
                algorithms=[JWT_ALGORITHM],
                audience=INTERNAL_APIS_AUDIENCE,
                issuer=AUTH_API_ISSUER,
            )
        return TokenPayload(**payload)
    except ValueError:
        raise AuthError("Invalid token payload")
    except Exception as exc:
        if JWT_BACKEND == "pyjwt" and pyjwt is not None:
            if isinstance(exc, pyjwt.ExpiredSignatureError):
                raise AuthError("Token expired") from exc
            if isinstance(exc, pyjwt.InvalidTokenError):
                raise AuthError("Invalid token") from exc
        else:
            if isinstance(exc, JoseExpiredSignatureError):
                raise AuthError("Token expired") from exc
            if isinstance(exc, JoseJWTError):
                raise AuthError("Invalid token") from exc
        raise


def require_role(*allowed_roles: str) -> Callable[[TokenPayload], TokenPayload]:
    """Dependency to check if user has one of the allowed roles."""

    def dependency(token: TokenPayload = Depends(verify_jwt)) -> TokenPayload:
        if token.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{token.role}' does not have access. Required: {allowed_roles}",
            )
        return token

    return dependency


def require_permission(*required_permissions: str) -> Callable[[TokenPayload], TokenPayload]:
    """Dependency to check if user has all required permissions."""

    def dependency(token: TokenPayload = Depends(verify_jwt)) -> TokenPayload:
        user_permissions = set(token.permissions)
        required = set(required_permissions)

        if not required.issubset(user_permissions):
            missing = required - user_permissions
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {missing}",
            )
        return token

    return dependency


def require_role_or_permission(
    roles: Optional[list[str]] = None,
    permissions: Optional[list[str]] = None,
) -> Callable[[TokenPayload], TokenPayload]:
    """Dependency to check if user has required role OR permission."""

    def dependency(token: TokenPayload = Depends(verify_jwt)) -> TokenPayload:
        roles_match = False
        permissions_match = False

        if roles:
            roles_match = token.role in roles
        else:
            roles_match = True

        if permissions:
            permissions_match = any(p in token.permissions for p in permissions)
        else:
            permissions_match = True

        if not (roles_match or permissions_match):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return token

    return dependency
