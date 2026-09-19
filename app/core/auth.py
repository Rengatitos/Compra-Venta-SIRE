from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.domain.usuario import esta_permitido, normalizar_correo

bearer_scheme = HTTPBearer()

# Marca del esquema de sesión. El JWT anterior identificaba una empresa
# (`empresa_id` + `ruc`); este identifica a una persona. Exigir el claim es lo
# que invalida los tokens viejos que sigan vivos.
#
# La alternativa —rotar JWT_SECRET_KEY— sería un desastre silencioso:
# `app.core.encryption` usa `SOL_USER_CRYPTO_KEY or JWT_SECRET_KEY` como semilla
# de Fernet, así que en cualquier despliegue sin la primera, cambiar el secreto
# del JWT dejaría ilegibles todas las contraseñas SOL guardadas y tumbaría el
# scraping, las detracciones y la renovación del token de SUNAT.
TIPO_TOKEN = "usuario"


def create_token(email: str, nombre: str | None = None, foto: str | None = None) -> str:
    # `nombre` y `foto` se aceptan por comodidad de quien llama pero no entran
    # en el payload: viajan en el cuerpo de la respuesta de login, para no
    # engordar la cabecera Authorization de todas las peticiones siguientes.
    payload = {
        "tipo": TIPO_TOKEN,
        "sub": email,
        "email": email,
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


async def usuario_actual(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> dict:
    """La persona autenticada. No toca Mongo: el panel no tiene usuarios en base.

    Sustituye a `empresa_autenticada`. La diferencia de fondo es que el token ya
    no aporta el sujeto de datos, solo el permiso: la empresa sobre la que se
    actúa la resuelve `app.api.v1.deps.empresa_actual` a partir del RUC del path.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado. Usa 'Authorization: Bearer <token>'",
        )

    payload = decode_token(credentials.credentials)

    if payload.get("tipo") != TIPO_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de un esquema de sesión anterior. Vuelve a iniciar sesión.",
        )

    correo = normalizar_correo(payload.get("email"))
    if not correo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido: sin correo"
        )

    # La allowlist se revalida en cada petición, no solo al iniciar sesión: así
    # quitar un correo de GOOGLE_ALLOWED_EMAILS lo expulsa en el acto en vez de
    # dejarlo dentro hasta que caduque su token.
    if not esta_permitido(correo, settings.GOOGLE_ALLOWED_EMAILS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta no está autorizada para usar el panel",
        )

    return {"email": correo}
