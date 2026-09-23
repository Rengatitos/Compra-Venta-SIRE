import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import create_token, rol_de, usuario_actual
from app.db.database import get_db
from app.schemas.auth import LoginGoogle, TokenResponse, UsuarioResponse
from app.services import google_oauth

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post("/google", response_model=TokenResponse, summary="Iniciar sesión con Google")
# El login anterior no tenía límite pese a ser el endpoint más atacable. Éste va
# más holgado que el 5/min del alta de empresa porque cerrar el diálogo de
# Google y volver a intentarlo es una maniobra normal del usuario.
@limiter.limit("10/minute")
async def login_google(request: Request, payload: LoginGoogle, db=Depends(get_db)):
    try:
        datos = await google_oauth.verificar_id_token(payload.credential)
    except google_oauth.ErrorRedGoogle:
        # 503 y no 401: si Google no responde, el token del usuario no tiene
        # nada de malo, y devolver 401 mandaría a buscar el problema en el sitio
        # equivocado.
        logger.exception("No se pudo validar el ID token contra Google")
        raise HTTPException(
            status_code=503,
            detail="No se pudo contactar con Google para validar la sesión",
        ) from None
    except google_oauth.ErrorIdTokenGoogle as exc:
        logger.warning("ID token de Google rechazado: %s", exc)
        raise HTTPException(status_code=401, detail="Token de Google inválido") from None

    correo = datos["email"]
    rol = await rol_de(db, correo)
    if rol is None:
        # Autenticado pero no autorizado, así que 403. Es la única traza que
        # queda de un intento de acceso, de ahí el warning.
        logger.warning("Acceso denegado a %s: no tiene acceso al panel", correo)
        raise HTTPException(
            status_code=403,
            detail="Esta cuenta de Google no tiene acceso al panel",
        )

    logger.info("Sesión iniciada por %s", correo)
    return TokenResponse(
        access_token=create_token(email=correo, nombre=datos.get("nombre")),
        usuario=UsuarioResponse(
            email=correo,
            nombre=datos.get("nombre"),
            foto=datos.get("foto"),
            rol=rol.value,
        ),
    )


@router.get("/yo", response_model=UsuarioResponse, summary="Quién soy y con qué rol")
async def yo(usuario: dict = Depends(usuario_actual)):
    """El panel lo consulta al cargar para saber si mostrar la gestión de
    accesos: el rol puede cambiar mientras la sesión sigue abierta."""
    return UsuarioResponse(email=usuario["email"], rol=usuario["rol"])
