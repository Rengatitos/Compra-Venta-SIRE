"""Solicitudes de procesamiento masivo, sus envíos de correo y el enlace
público de descarga del ZIP."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.auth import leer_token_descarga, usuario_actual
from app.db.database import get_db
from app.repositories import solicitudes as repo_solicitudes
from app.schemas.solicitudes import EnvioListado, SolicitudCreate, SolicitudResponse
from app.services import empaquetado_service, solicitudes_service
from app.services.solicitudes_service import SolicitudInvalida

router = APIRouter(dependencies=[Depends(usuario_actual)])
router_correos = APIRouter(dependencies=[Depends(usuario_actual)])
# Sin sesión: la autoriza el token firmado del propio enlace.
router_descargas = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "",
    response_model=SolicitudResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Procesar empresas y periodos en segundo plano",
)
@limiter.limit("10/minute")
async def crear_solicitud(
    request: Request,
    datos: SolicitudCreate,
    usuario: dict = Depends(usuario_actual),
    db=Depends(get_db),
):
    """Encola, por cada empresa y periodo: descarga SIRE, comprobantes y
    clasificación con IA. Al terminar todo se arma el ZIP y se envía por
    correo. El contador puede cerrar la página: sigue en el servidor."""
    try:
        solicitud = await solicitudes_service.crear(
            db,
            creado_por=usuario["email"],
            empresas=datos.empresas,
            periodos=datos.periodos,
            clasificar=datos.clasificar,
        )
    except SolicitudInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await solicitudes_service.detalle(db, solicitud)


@router.get("", response_model=list[SolicitudResponse], summary="Solicitudes recientes")
async def listar_solicitudes(db=Depends(get_db)):
    return [
        await solicitudes_service.detalle(db, s, con_jobs=False)
        for s in await repo_solicitudes.listar(db)
    ]


async def _solicitud(db, solicitud_id: str) -> dict:
    solicitud = await repo_solicitudes.obtener(db, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


@router.get("/{solicitud_id}", response_model=SolicitudResponse, summary="Estado de una solicitud")
async def obtener_solicitud(solicitud_id: str, db=Depends(get_db)):
    return await solicitudes_service.detalle(db, await _solicitud(db, solicitud_id))


@router.post(
    "/{solicitud_id}/reintentar",
    response_model=SolicitudResponse,
    summary="Volver a encolar lo que falló",
)
async def reintentar_solicitud(solicitud_id: str, db=Depends(get_db)):
    await _solicitud(db, solicitud_id)
    try:
        solicitud = await solicitudes_service.reintentar(db, solicitud_id)
    except SolicitudInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await solicitudes_service.detalle(db, solicitud)


def _archivo(solicitud_id: str, nombre: str) -> FileResponse:
    raiz = empaquetado_service.raiz_solicitud(solicitud_id).resolve()
    ruta = (raiz / nombre).resolve()
    if not ruta.is_relative_to(raiz) or ruta.suffix != ".zip" or not ruta.is_file():
        raise HTTPException(status_code=404, detail="El archivo ya no está disponible")
    return FileResponse(ruta, media_type="application/zip", filename=ruta.name)


@router.get("/{solicitud_id}/zip", response_class=FileResponse, summary="Descargar el ZIP")
async def descargar_zip(solicitud_id: str, db=Depends(get_db)):
    solicitud = await _solicitud(db, solicitud_id)
    if not solicitud.get("zip"):
        raise HTTPException(status_code=409, detail="El ZIP aún no está listo")
    return _archivo(solicitud_id, solicitud["zip"]["archivo"])


@router_correos.get(
    "/envios",
    response_model=list[EnvioListado],
    summary="Correos enviados con los resultados de las solicitudes",
)
async def listar_envios(db=Depends(get_db)):
    return await repo_solicitudes.listar_envios(db)


@router_descargas.get(
    "/{token}",
    response_class=FileResponse,
    summary="Descargar el ZIP desde el enlace del correo",
)
@limiter.limit("20/minute")
async def descargar_con_enlace(request: Request, token: str):
    payload = leer_token_descarga(token)
    return _archivo(payload["sid"], payload.get("archivo") or "")
