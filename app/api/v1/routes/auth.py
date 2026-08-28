import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import create_token
from app.core.encryption import decrypt_password
from app.db.database import get_db
from app.repositories import empresas as repo_empresas
from app.schemas.empresa import EmpresaLogin, TokenResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión y obtener JWT")
async def login(payload: EmpresaLogin, db=Depends(get_db)):
    empresa = await repo_empresas.obtener_por_ruc(db, payload.ruc)

    valido = False
    if empresa and empresa.get("usuario") == payload.usuario:
        try:
            valido = decrypt_password(empresa.get("password", "")) == payload.password
        except Exception:
            valido = False

    if not valido:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    return TokenResponse(
        access_token=create_token(empresa_id=str(empresa["_id"]), ruc=empresa["ruc"])
    )
