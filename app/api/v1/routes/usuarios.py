"""Gestión de quién tiene acceso al panel. Solo administradores."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, field_validator

from app.core.auth import exigir_admin
from app.core.config import settings
from app.db.database import get_db
from app.domain.usuario import Rol, esta_permitido, normalizar_correo
from app.repositories import usuarios as repo_usuarios

router = APIRouter()
logger = logging.getLogger(__name__)


class UsuarioAcceso(BaseModel):
    email: str
    rol: Rol
    # `True` para los administradores de GOOGLE_ALLOWED_EMAILS: no se pueden
    # cambiar ni quitar desde aquí.
    fijo: bool = False
    agregado_por: str | None = None
    agregado_en: datetime | None = None


class AltaUsuario(BaseModel):
    email: str
    rol: Rol = Rol.USUARIO

    @field_validator("email")
    @classmethod
    def validar_correo(cls, v: str) -> str:
        v = normalizar_correo(v)
        local, arroba, dominio = v.partition("@")
        if not local or not arroba or "." not in dominio or " " in v:
            raise ValueError("Correo no válido")
        return v


class CambioRol(BaseModel):
    rol: Rol


def _no_fijo(correo: str) -> None:
    if esta_permitido(correo, settings.GOOGLE_ALLOWED_EMAILS):
        raise HTTPException(
            status_code=409,
            detail="Es un administrador fijo (GOOGLE_ALLOWED_EMAILS): se cambia en el servidor",
        )


@router.get("", response_model=list[UsuarioAcceso], summary="Correos con acceso al panel")
async def listar(_admin: dict = Depends(exigir_admin), db=Depends(get_db)):
    fijos = sorted({normalizar_correo(c) for c in settings.GOOGLE_ALLOWED_EMAILS})
    salida = [UsuarioAcceso(email=c, rol=Rol.ADMIN, fijo=True) for c in fijos]
    salida += [
        UsuarioAcceso(**u) for u in await repo_usuarios.listar(db) if u["email"] not in fijos
    ]
    return salida


@router.post("", response_model=UsuarioAcceso, status_code=201, summary="Dar acceso a un correo")
async def agregar(datos: AltaUsuario, admin: dict = Depends(exigir_admin), db=Depends(get_db)):
    _no_fijo(datos.email)
    if await repo_usuarios.rol_de(db, datos.email) is not None:
        raise HTTPException(status_code=409, detail="Ese correo ya tiene acceso")
    guardado = await repo_usuarios.guardar(db, datos.email, datos.rol, admin["email"])
    logger.info("Acceso concedido a %s (%s) por %s", datos.email, datos.rol.value, admin["email"])
    return UsuarioAcceso(**guardado)


@router.patch("/{email}", response_model=UsuarioAcceso, summary="Cambiar el rol de un correo")
async def cambiar_rol(
    datos: CambioRol,
    email: str = Path(...),
    admin: dict = Depends(exigir_admin),
    db=Depends(get_db),
):
    correo = normalizar_correo(email)
    _no_fijo(correo)
    if await repo_usuarios.rol_de(db, correo) is None:
        raise HTTPException(status_code=404, detail="Ese correo no tiene acceso")
    if correo == admin["email"] and datos.rol != Rol.ADMIN:
        # Quitarse el rol a uno mismo deja la sesión a medias y es casi siempre
        # un clic equivocado: que lo haga otro administrador.
        raise HTTPException(status_code=409, detail="No puedes quitarte tu propio rol de admin")
    guardado = await repo_usuarios.guardar(db, correo, datos.rol, admin["email"])
    logger.info("Rol de %s cambiado a %s por %s", correo, datos.rol.value, admin["email"])
    return UsuarioAcceso(**guardado)


@router.delete("/{email}", status_code=204, summary="Quitar el acceso a un correo")
async def quitar(email: str = Path(...), admin: dict = Depends(exigir_admin), db=Depends(get_db)):
    correo = normalizar_correo(email)
    _no_fijo(correo)
    if correo == admin["email"]:
        raise HTTPException(status_code=409, detail="No puedes quitarte el acceso a ti mismo")
    if not await repo_usuarios.eliminar(db, correo):
        raise HTTPException(status_code=404, detail="Ese correo no tiene acceso")
    logger.info("Acceso retirado a %s por %s", correo, admin["email"])
