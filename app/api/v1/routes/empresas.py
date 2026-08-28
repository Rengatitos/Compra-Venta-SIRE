import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual
from app.core.auth import verify_admin
from app.core.encryption import decrypt_password, encrypt_password
from app.db.database import get_db
from app.domain import rubro as dominio_rubro
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import empresas as repo_empresas
from app.repositories import periodos as repo_periodos
from app.repositories import vectores as repo_vectores
from app.schemas.empresa import EmpresaCreate, EmpresaResponse, EmpresaUpdate
from app.schemas.generic import MessageResponse, StatusResponse
from app.services.sunat.auth import credenciales_cliente, obtener_token

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


def _con_rubro(empresa: dict) -> dict:
    empresa["rubro"] = dominio_rubro.desde_token_sunat(empresa.get("sunat_token", ""))
    return empresa


@router.post("", response_model=EmpresaResponse, summary="Registrar empresa")
@limiter.limit("5/minute")
async def crear_empresa(request: Request, datos: EmpresaCreate, db=Depends(get_db)):
    if await repo_empresas.obtener_por_ruc(db, datos.ruc):
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese RUC")

    creada = await repo_empresas.crear(
        db,
        {
            "ruc": datos.ruc,
            "usuario": datos.usuario,
            "password": encrypt_password(datos.password),
            "sunat_token": None,
            "sunat_client_id": datos.sunat_client_id,
            "sunat_client_secret": datos.sunat_client_secret,
        },
    )
    return _con_rubro(creada)


@router.get(
    "",
    response_model=list[EmpresaResponse],
    dependencies=[Depends(verify_admin)],
    summary="Listar empresas (admin)",
)
async def listar_empresas(db=Depends(get_db)):
    return [_con_rubro(e) for e in await repo_empresas.listar(db)]


@router.get("/{ruc}", response_model=EmpresaResponse, summary="Consultar empresa")
async def leer_empresa(empresa: dict = Depends(empresa_actual)):
    return _con_rubro(empresa)


@router.put("/{ruc}", response_model=EmpresaResponse, summary="Actualizar empresa")
async def actualizar_empresa(
    datos: EmpresaUpdate,
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    cambios = datos.model_dump(exclude_unset=True)

    if "password" in cambios:
        cambios["password"] = encrypt_password(cambios["password"])

    # Un client_id/secret vacío significa "no lo toques", no "bórralo".
    for campo in ("sunat_client_id", "sunat_client_secret"):
        if campo in cambios and not cambios[campo]:
            cambios.pop(campo)

    actualizada = await repo_empresas.actualizar(db, empresa["_id"], cambios)
    return _con_rubro(actualizada)


@router.delete("/{ruc}", response_model=MessageResponse, summary="Eliminar empresa")
async def eliminar_empresa(empresa: dict = Depends(empresa_actual), db=Depends(get_db)):
    empresa_id = str(empresa["_id"])

    await repo_comprobantes.eliminar_de_empresa(db, empresa_id)
    await repo_periodos.eliminar_de_empresa(db, empresa_id)
    await repo_vectores.eliminar_de_empresa(db, empresa_id)

    if await repo_empresas.eliminar(db, empresa["_id"]) == 0:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    return {"mensaje": "Empresa y datos asociados eliminados"}


@router.post(
    "/{ruc}/token-sunat",
    response_model=StatusResponse,
    summary="Renovar el token Bearer de SUNAT",
)
async def renovar_token_sunat(empresa: dict = Depends(empresa_actual), db=Depends(get_db)):
    client_id, client_secret = credenciales_cliente(empresa)
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="La empresa no tiene sunat_client_id/sunat_client_secret configurados",
        )

    try:
        password = decrypt_password(empresa["password"])
    except Exception:
        raise HTTPException(
            status_code=500, detail="No se pudo descifrar la contraseña SOL almacenada"
        ) from None

    token, error = await obtener_token(
        empresa["ruc"], empresa["usuario"], password, client_id, client_secret
    )
    if not token:
        raise HTTPException(status_code=502, detail=f"SUNAT no devolvió un token: {error}")

    await repo_empresas.guardar_token_sunat(db, empresa["_id"], token)
    return {"estado": "exito", "mensaje": "Token de SUNAT actualizado correctamente"}
