"""Cuentas de API para integraciones (ELT, scripts). Solo administradores.

Una cuenta de API entra con correo y contraseña por `POST /auth/token`, sin
Google. La contraseña la genera Sire, se muestra una sola vez (al crearla o
regenerarla) y solo se guarda su hash. Vence a los `vigencia_dias`.

Tienen acceso completo a la API (rol admin): un solo correo y contraseña sirve
para todas las rutas.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, field_validator

from app.core import claves
from app.core.auth import exigir_admin
from app.db.database import get_db
from app.domain.usuario import normalizar_correo
from app.repositories import cuentas_api as repo_cuentas_api

router = APIRouter()
logger = logging.getLogger(__name__)


class CuentaApi(BaseModel):
    email: str
    vigencia_dias: int
    expira_en: datetime
    vigente: bool
    creada_por: str | None = None
    creada_en: datetime | None = None
    clave_generada_en: datetime | None = None
    ultimo_uso_en: datetime | None = None


class CuentaApiConClave(BaseModel):
    cuenta: CuentaApi
    # Solo en esta respuesta: Sire no la guarda y no se puede volver a consultar.
    password: str


class AltaCuentaApi(BaseModel):
    email: str
    vigencia_dias: int = Field(90, ge=1, le=365)

    @field_validator("email")
    @classmethod
    def validar_correo(cls, v: str) -> str:
        v = normalizar_correo(v)
        local, arroba, dominio = v.partition("@")
        if not local or not arroba or "." not in dominio or " " in v:
            raise ValueError("Correo no válido")
        return v


class Regenerar(BaseModel):
    vigencia_dias: int | None = Field(None, ge=1, le=365)


def _salida(documento: dict) -> CuentaApi:
    return CuentaApi(**documento, vigente=repo_cuentas_api.vigente(documento))


@router.get("", response_model=list[CuentaApi], summary="Cuentas de API")
async def listar(_admin: dict = Depends(exigir_admin), db=Depends(get_db)):
    return [_salida(c) for c in await repo_cuentas_api.listar(db)]


@router.post(
    "",
    response_model=CuentaApiConClave,
    status_code=201,
    summary="Crear una cuenta de API (devuelve su contraseña una sola vez)",
)
async def crear(datos: AltaCuentaApi, admin: dict = Depends(exigir_admin), db=Depends(get_db)):
    if await repo_cuentas_api.obtener(db, datos.email):
        raise HTTPException(
            status_code=409, detail="Esa cuenta de API ya existe: regenera su contraseña"
        )

    clave = claves.generar()
    documento = await repo_cuentas_api.guardar_clave(
        db,
        datos.email,
        clave_hash=claves.hashear(clave),
        vigencia_dias=datos.vigencia_dias,
        por=admin["email"],
    )
    logger.info("Cuenta de API %s creada por %s", datos.email, admin["email"])
    return {"cuenta": _salida(documento), "password": clave}


@router.post(
    "/{email}/regenerar",
    response_model=CuentaApiConClave,
    summary="Nueva contraseña para una cuenta de API (la anterior deja de servir)",
)
async def regenerar(
    datos: Regenerar,
    email: str = Path(...),
    admin: dict = Depends(exigir_admin),
    db=Depends(get_db),
):
    cuenta = await repo_cuentas_api.obtener(db, email)
    if cuenta is None:
        raise HTTPException(status_code=404, detail="No existe esa cuenta de API")

    clave = claves.generar()
    documento = await repo_cuentas_api.guardar_clave(
        db,
        cuenta["email"],
        clave_hash=claves.hashear(clave),
        vigencia_dias=datos.vigencia_dias or cuenta.get("vigencia_dias") or 90,
        por=admin["email"],
    )
    logger.info(
        "Contraseña de la cuenta de API %s regenerada por %s", cuenta["email"], admin["email"]
    )
    return {"cuenta": _salida(documento), "password": clave}


@router.delete("/{email}", status_code=204, summary="Eliminar una cuenta de API")
async def eliminar(email: str = Path(...), admin: dict = Depends(exigir_admin), db=Depends(get_db)):
    if not await repo_cuentas_api.eliminar(db, email):
        raise HTTPException(status_code=404, detail="No existe esa cuenta de API")
    logger.info("Cuenta de API %s eliminada por %s", normalizar_correo(email), admin["email"])
