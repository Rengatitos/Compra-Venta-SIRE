import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core import claves
from app.core.auth import create_token, rol_de, usuario_actual
from app.db.database import get_db
from app.domain.usuario import Rol
from app.repositories import cuentas_api as repo_cuentas_api
from app.schemas.auth import LoginCuentaApi, LoginGoogle, TokenResponse, UsuarioResponse
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
    # Una cuenta de API no entra con Google aunque exista un buzón con ese nombre.
    rol = await rol_de(db, correo, cuentas_api=False)
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


# Una sola respuesta para correo inexistente y contraseña mala: no revela qué
# cuentas existen.
CREDENCIALES_MALAS = "Correo o contraseña incorrectos"
# Con un correo que no existe también se calcula un scrypt, para que el tiempo
# de respuesta no delate si la cuenta existe.
_HASH_RELLENO = claves.hashear(claves.generar())


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Token para integraciones con correo y contraseña (cuentas de API)",
)
@limiter.limit("5/minute")
async def login_cuenta_api(request: Request, payload: LoginCuentaApi, db=Depends(get_db)):
    """Para programas (ELT, scripts): sin Google y sin abrir el panel.

    Solo sirve para las cuentas de API que un administrador crea en el panel
    («Accesos» › «Cuentas de API»); las personas entran con Google. Devuelve el
    mismo token que el login con Google, con la misma vigencia.
    """
    cuenta = await repo_cuentas_api.obtener(db, payload.email)
    guardado = cuenta["clave_hash"] if cuenta else _HASH_RELLENO
    valida = claves.verificar(payload.password, guardado)
    if cuenta is None or not valida:
        logger.warning("Login de cuenta de API rechazado: %s", payload.email)
        raise HTTPException(status_code=401, detail=CREDENCIALES_MALAS)
    if not repo_cuentas_api.vigente(cuenta):
        raise HTTPException(
            status_code=401,
            detail="La contraseña de esta cuenta venció: un administrador debe generar una nueva",
        )

    await repo_cuentas_api.marcar_uso(db, cuenta["email"])
    logger.info("Token emitido para la cuenta de API %s", cuenta["email"])
    return TokenResponse(
        access_token=create_token(email=cuenta["email"]),
        usuario=UsuarioResponse(email=cuenta["email"], rol=Rol(cuenta["rol"]).value),
    )


@router.get("/yo", response_model=UsuarioResponse, summary="Quién soy y con qué rol")
async def yo(usuario: dict = Depends(usuario_actual)):
    """El panel lo consulta al cargar para saber si mostrar la gestión de
    accesos: el rol puede cambiar mientras la sesión sigue abierta."""
    return UsuarioResponse(email=usuario["email"], rol=usuario["rol"])
