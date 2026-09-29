from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.db.database import get_db
from app.domain.usuario import Rol, normalizar_correo, resolver_rol
from app.repositories import cuentas_api as repo_cuentas_api
from app.repositories import usuarios as repo_usuarios

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

# Con qué se obtuvo el token. Un mismo correo puede entrar con Google (con el rol
# de la persona) y a la vez tener una cuenta de API (acceso completo): el token
# lleva su origen para que la sesión de Google no herede los permisos de la API.
ORIGEN_GOOGLE = "google"
ORIGEN_API = "api"


def create_token(
    email: str,
    nombre: str | None = None,
    foto: str | None = None,
    horas: int | None = None,
    origen: str | None = None,
) -> str:
    # `nombre` y `foto` se aceptan por comodidad de quien llama pero no entran
    # en el payload: viajan en el cuerpo de la respuesta de login, para no
    # engordar la cabecera Authorization de todas las peticiones siguientes.
    payload = {
        "tipo": TIPO_TOKEN,
        "sub": email,
        "email": email,
        "exp": datetime.now(UTC) + timedelta(hours=horas or settings.JWT_EXPIRE_HOURS),
    }
    if origen:
        payload["origen"] = origen
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


# Enlace del correo de una solicitud. Lleva su propio `tipo` para que no sirva
# como sesión (`usuario_actual` exige `usuario`) y solo abre un archivo concreto.
TIPO_TOKEN_DESCARGA = "descarga"


def crear_token_descarga(solicitud_id: str, archivo: str, dias: int) -> str:
    payload = {
        "tipo": TIPO_TOKEN_DESCARGA,
        "sid": solicitud_id,
        "archivo": archivo,
        "exp": datetime.now(UTC) + timedelta(days=dias),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def leer_token_descarga(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("tipo") != TIPO_TOKEN_DESCARGA or not payload.get("sid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Enlace inválido")
    return payload


async def rol_de(db, correo: str, *, cuentas_api: bool = True, personas: bool = True) -> Rol | None:
    """Rol con el que entra ese correo, o `None` si no tiene acceso.

    Los administradores fijos del entorno se resuelven sin tocar Mongo.
    `personas=False` mira solo las cuentas de API.
    """
    if not personas:
        return resolver_rol(correo, [], await repo_cuentas_api.rol_de(db, correo))
    rol = resolver_rol(correo, settings.GOOGLE_ALLOWED_EMAILS, None)
    if rol is not None:
        return rol
    rol = resolver_rol(correo, [], await repo_usuarios.rol_de(db, correo))
    if rol is not None or not cuentas_api:
        return rol
    # Cuentas de API (integraciones): solo mientras su contraseña esté vigente.
    # Se revisa en cada petición, así que borrarla o dejarla vencer corta
    # también los tokens que ya había emitido.
    return resolver_rol(correo, [], await repo_cuentas_api.rol_de(db, correo))


async def usuario_actual(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db=Depends(get_db),
) -> dict:
    """La persona autenticada y su rol (`app.domain.usuario`).

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

    # El acceso se revalida en cada petición, no solo al iniciar sesión: así
    # quitar un correo (del entorno o desde el panel) lo expulsa en el acto en
    # vez de dejarlo dentro hasta que caduque su token.
    # Token de cuenta de API: solo esa cuenta. Token de Google: solo la persona.
    # Sin origen (tokens emitidos antes de marcarlo): como antes, ambas.
    origen = payload.get("origen")
    rol = await rol_de(
        db,
        correo,
        cuentas_api=origen != ORIGEN_GOOGLE,
        personas=origen != ORIGEN_API,
    )
    if rol is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta no está autorizada para usar el panel",
        )

    return {"email": correo, "rol": rol.value}


async def exigir_admin(usuario: dict = Depends(usuario_actual)) -> dict:
    """Solo administradores: gestionar quién tiene acceso al panel."""
    if usuario["rol"] != Rol.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede gestionar los accesos",
        )
    return usuario
