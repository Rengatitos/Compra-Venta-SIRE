from datetime import datetime, timezone
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import create_token, require_same_user, verify_admin, verify_user
from app.core.encryption import encrypt_password, decrypt_password
from app.db.database import get_user_db
from app.schemas.user import (
    SolUserCreate,
    SolUserCreateResponse,
    SolUserLogin,
    SolUserResponse,
    SolUserUpdate,
    TokenResponse,
)
from app.schemas.generic import MessageResponse, StatusResponse

router = APIRouter()
logger = logging.getLogger(__name__)


limiter = Limiter(key_func=get_remote_address)


_RUBROS_POR_PREFIJO_CIIU = {
    "62": "Tecnología / Informática",
    "55": "Restaurantes / Alimentación",
    "56": "Restaurantes / Alimentación",
    "41": "Construcción",
    "42": "Construcción",
    "43": "Construcción",
    "45": "Comercio",
    "46": "Comercio",
    "47": "Comercio",
    "49": "Transporte",
    "50": "Transporte",
    "51": "Transporte",
    "69": "Servicios Profesionales",
    "70": "Servicios Profesionales",
    "71": "Servicios Profesionales",
    "86": "Salud",
    "87": "Salud",
    "88": "Salud",
    "85": "Educación",
    "01": "Agropecuario",
    "02": "Agropecuario",
    "03": "Agropecuario",
    "10": "Manufactura",
    "11": "Manufactura",
    "31": "Manufactura",
    "64": "Finanzas",
    "65": "Finanzas",
    "66": "Finanzas",
}


def _get_rubro_from_ciiu(ciiu: str) -> str:
    if not ciiu:
        return "General"
    ciiu = str(ciiu).strip()
    return _RUBROS_POR_PREFIJO_CIIU.get(ciiu[:2], "Servicios Generales")


def _extract_rubro(token: str) -> str:
    if not token:
        return "General"
    try:
        import jwt

        payload = jwt.decode(token, options={"verify_signature": False})
        ciiu = payload.get("userdata", {}).get("map", {}).get("ddpData", {}).get("ddp_ciiu", "")
        return _get_rubro_from_ciiu(ciiu)
    except Exception:
        return "General"


@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión y obtener JWT")
async def login(payload: SolUserLogin, db=Depends(get_user_db)):
    """Login con RUC + usuario + contraseña. Devuelve un JWT Bearer."""
    user = await db["sol_users"].find_one({"ruc": payload.ruc, "usuario": payload.usuario})
    stored = user.get("password", "") if user else ""
    try:
        valid = user is not None and decrypt_password(stored) == payload.password
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = create_token(
        user_id=str(user["_id"]),
        ruc=user["ruc"],
    )
    return TokenResponse(access_token=token)


@router.post("/", response_model=SolUserCreateResponse, summary="Crear usuario SOL")
@limiter.limit("5/minute")
async def create_user(
    request: Request,
    user: SolUserCreate,
    db=Depends(get_user_db),
):
    """Crea un nuevo usuario SOL."""
    collection = db["sol_users"]
    existing = await collection.find_one({"ruc": user.ruc, "usuario": user.usuario})
    if existing:
        raise HTTPException(status_code=400, detail="El usuario ya existe para este RUC")

    new_user = {
        "ruc": user.ruc,
        "usuario": user.usuario,
        "password": encrypt_password(user.password),
        "sunat_token": user.sunat_token,
        "sunat_client_id": user.sunat_client_id,
        "sunat_client_secret": user.sunat_client_secret,
        "tenant_id": user.tenant_id,
        "cliente_id": user.cliente_id,
        "cuenta_id": user.cuenta_id,
        "fecha_creacion": datetime.now(timezone.utc).isoformat(),
    }
    result = await collection.insert_one(new_user)
    created = await collection.find_one({"_id": result.inserted_id})
    return created


@router.get("/", response_model=List[SolUserResponse], dependencies=[Depends(verify_admin)])
async def list_users(db=Depends(get_user_db)):
    collection = db["sol_users"]
    users = await collection.find().to_list(length=100)
    return users


@router.get("/{user_id}", response_model=SolUserResponse)
async def read_user(user_id: str, db=Depends(get_user_db), user=Depends(require_same_user)):
    user["rubro"] = _extract_rubro(user.get("sunat_token", ""))
    return user


@router.put("/{user_id}", response_model=SolUserResponse)
async def update_user(
    user_id: str,
    user_update: SolUserUpdate,
    db=Depends(get_user_db),
    user=Depends(require_same_user),
):
    collection = db["sol_users"]
    update_data = user_update.model_dump(exclude_unset=True)

    if "password" in update_data:
        update_data["password"] = encrypt_password(update_data["password"])

    if "sunat_client_id" in update_data and not update_data["sunat_client_id"]:
        update_data.pop("sunat_client_id")
    if "sunat_client_secret" in update_data and not update_data["sunat_client_secret"]:
        update_data.pop("sunat_client_secret")

    if not update_data:
        return user

    await collection.update_one({"_id": user["_id"]}, {"$set": update_data})
    return await collection.find_one({"_id": user["_id"]})


@router.delete("/{user_id}", response_model=MessageResponse)
async def delete_user(user_id: str, db=Depends(get_user_db), user=Depends(require_same_user)):
    collection = db["sol_users"]
    result = await collection.delete_one({"_id": user["_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    try:
        await db["periodos"].delete_many({"user_id": str(user["_id"])})
        await db["facturas"].delete_many({"user_id": str(user["_id"])})
    except Exception as e:
        logger.error(f"Error borrando periodos/facturas asociados a {user_id}: {e}")

    return {"mensaje": "Usuario eliminado exitosamente"}


@router.delete(
    "/cleanup/{tenant_id}/{cliente_id}/{cuenta_id}",
    response_model=MessageResponse,
    summary="Eliminar todos los usuarios y facturas asociados a una cuenta SUNAT",
    dependencies=[Depends(verify_admin)],
)
async def cleanup_sol_user(tenant_id: str, cliente_id: str, cuenta_id: str, db=Depends(get_user_db)):
    collection = db["sol_users"]
    users = await collection.find({"tenant_id": tenant_id, "cliente_id": cliente_id, "cuenta_id": cuenta_id}).to_list(length=100)

    if not users:
        return {"mensaje": "No se encontraron usuarios en automat para esta cuenta"}

    for user_doc in users:
        user_id_str = str(user_doc["_id"])

        try:
            await db["periodos"].delete_many({"user_id": user_id_str})
            await db["facturas"].delete_many({"user_id": user_id_str})
        except Exception as e:
            logger.error(f"Error borrando dependencias para usuario {user_id_str}: {e}")

        await collection.delete_one({"_id": user_doc["_id"]})

    return {"mensaje": f"Se eliminaron {len(users)} usuarios de automat y sus datos vinculados."}


@router.post("/{user_id}/refresh-token", response_model=StatusResponse, summary="Renovar token Bearer de SUNAT")
async def refresh_sunat_token(
    user_id: str,
    db=Depends(get_user_db),
    user=Depends(require_same_user),
):
    """
    Obtiene un nuevo token Bearer de SUNAT usando las credenciales OAuth
    almacenadas en la BD del usuario.
    """
    from app.services.sire_service import obtener_token_api_oficial

    ruc = user.get("ruc")
    usuario = user.get("usuario")
    password_encriptado = user.get("password")
    client_id = user.get("sunat_client_id")
    client_secret = user.get("sunat_client_secret")

    if not ruc or not usuario or not password_encriptado:
        raise HTTPException(status_code=400, detail="El usuario no tiene RUC, usuario o contraseña registrados")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="El usuario no tiene sunat_client_id/sunat_client_secret en BD. Regístralos manualmente antes de continuar.",
        )

    try:
        password_real = decrypt_password(password_encriptado)
    except Exception:
        raise HTTPException(status_code=500, detail="Error al desencriptar la contraseña del usuario")

    bearer_token, error = await obtener_token_api_oficial(ruc, usuario, password_real, client_id, client_secret)
    if not bearer_token:
        raise HTTPException(status_code=502, detail=f"SUNAT no devolvió un access_token válido: {error}")

    await db["sol_users"].update_one(
        {"_id": user["_id"]},
        {"$set": {
            "sunat_token": bearer_token,
        }},
    )

    return {"estado": "éxito", "mensaje": "Token de SUNAT actualizado correctamente"}
