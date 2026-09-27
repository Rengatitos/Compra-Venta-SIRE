import io
import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual
from app.core.auth import usuario_actual
from app.core.encryption import decrypt_password, encrypt_password
from app.db.database import get_db
from app.domain import rubro as dominio_rubro
from app.domain.carga_empresas import EstadoFila, FilaCarga, Modalidad, Motivo
from app.repositories import cargas_empresas as repo_cargas
from app.repositories import clasificaciones_frecuentes as repo_frecuentes
from app.repositories import codigos_vinculacion as repo_codigos_vinculacion
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import comprobantes_externos as repo_comprobantes_externos
from app.repositories import empresas as repo_empresas
from app.repositories import periodos as repo_periodos
from app.repositories import plan_cuentas as repo_plan_cuentas
from app.schemas.carga_empresas import CargaAceptada, CargaResponse, CargaResumen
from app.schemas.empresa import EmpresaCreada, EmpresaCreate, EmpresaResponse, EmpresaUpdate
from app.schemas.generic import MessageResponse, StatusResponse
from app.services import (
    carga_empresas_service,
    credenciales_sunat_service,
    ficha_ruc_service,
    imagenes_externas,
)
from app.services.carga_empresas_service import CredencialesApi, ExcelInvalido
from app.services.scraping_sunat import CredencialesSolError, SesionSolError
from app.services.sunat.auth import credenciales_cliente, obtener_token
from app.services.sunat.credenciales_api import CredencialesApiError, SinRecursoSire
from app.services.sunat.ficha_ruc import FichaNoEncontrada

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


MAX_BYTES_EXCEL = 2 * 1024 * 1024
EXTENSIONES_EXCEL = (".xlsx", ".xlsm")
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _con_rubro(empresa: dict) -> dict:
    # El rubro se guarda al completar el alta; las empresas de antes no lo
    # tienen y se sigue sacando del token.
    if not empresa.get("rubro"):
        empresa["rubro"] = dominio_rubro.desde_token_sunat(empresa.get("sunat_token", ""))
    return empresa


def _excel(contenido: bytes, nombre: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type=TIPO_XLSX,
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )


@router.post(
    "",
    response_model=EmpresaCreada,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar empresa",
)
@limiter.limit("5/minute")
async def crear_empresa(
    request: Request,
    datos: EmpresaCreate,
    usuario: dict = Depends(usuario_actual),
    db=Depends(get_db),
):
    """Alta individual. Responde en cuanto la empresa existe; el token y el
    CIIU se completan en segundo plano y su avance se sigue en
    `GET /empresas/cargas/{carga_id}`."""
    if await repo_empresas.obtener_por_ruc(db, datos.ruc):
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese RUC")

    fila = FilaCarga(1, datos.nombre or "", datos.ruc, datos.usuario, datos.password)
    carga = await carga_empresas_service.registrar(
        db,
        [fila],
        modalidad=Modalidad.INDIVIDUAL,
        registrado_por=usuario["email"],
        credenciales=CredencialesApi(datos.sunat_client_id, datos.sunat_client_secret),
    )
    [resultado] = carga["filas"]
    if resultado["estado"] == EstadoFila.NO_AGREGADA.value:
        if Motivo.RUC_EXISTENTE.value in resultado["motivos"]:
            raise HTTPException(status_code=409, detail="Ya existe una empresa con ese RUC")
        raise HTTPException(status_code=422, detail="; ".join(resultado["motivos"]))

    creada = await repo_empresas.obtener_por_ruc(db, datos.ruc)
    return {**_con_rubro(creada), "carga_id": str(carga["_id"])}


@router.post(
    "/cargas",
    response_model=CargaAceptada,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Registrar empresas desde un Excel",
)
@limiter.limit("3/minute")
async def cargar_empresas(
    request: Request,
    archivo: UploadFile = File(...),
    usuario: dict = Depends(usuario_actual),
    db=Depends(get_db),
):
    """Columnas A a D de la primera hoja: razón social, RUC, usuario y
    contraseña SOL. Las filas se validan al momento; las válidas se registran y
    sus datos de SUNAT se completan en la cola."""
    nombre = archivo.filename or "empresas.xlsx"
    if not nombre.lower().endswith(EXTENSIONES_EXCEL):
        raise HTTPException(status_code=400, detail="El archivo debe ser un Excel (.xlsx)")
    contenido = await archivo.read(MAX_BYTES_EXCEL + 1)
    if len(contenido) > MAX_BYTES_EXCEL:
        raise HTTPException(status_code=413, detail="El archivo pasa de 2 MB")
    try:
        filas = carga_empresas_service.leer_excel(contenido)
    except ExcelInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    carga = await carga_empresas_service.registrar(
        db, filas, modalidad=Modalidad.MASIVA, registrado_por=usuario["email"], archivo=nombre
    )
    return {"carga_id": str(carga["_id"])}


@router.get(
    "/cargas",
    response_model=list[CargaResumen],
    dependencies=[Depends(usuario_actual)],
    summary="Historial de cargas de empresas",
)
async def listar_cargas(db=Depends(get_db)):
    return await repo_cargas.listar(db)


@router.get(
    "/cargas/plantilla",
    dependencies=[Depends(usuario_actual)],
    summary="Plantilla vacía para la carga masiva",
    response_class=StreamingResponse,
)
async def plantilla_carga():
    return _excel(carga_empresas_service.plantilla(), "plantilla_empresas.xlsx")


@router.get(
    "/cargas/{carga_id}",
    response_model=CargaResponse,
    dependencies=[Depends(usuario_actual)],
    summary="Estado de una carga de empresas",
)
async def obtener_carga(carga_id: str, db=Depends(get_db)):
    carga = await repo_cargas.obtener(db, carga_id)
    if not carga:
        raise HTTPException(status_code=404, detail="Carga no encontrada")
    return carga


@router.get(
    "/cargas/{carga_id}/reporte",
    dependencies=[Depends(usuario_actual)],
    summary="Reporte en Excel de una carga de empresas",
    response_class=StreamingResponse,
)
async def reporte_carga(carga_id: str, db=Depends(get_db)):
    carga = await repo_cargas.obtener(db, carga_id)
    if not carga:
        raise HTTPException(status_code=404, detail="Carga no encontrada")
    fecha = carga["creado_en"].strftime("%Y%m%d_%H%M")
    return _excel(carga_empresas_service.reporte(carga), f"reporte_carga_{fecha}.xlsx")


@router.get(
    "",
    response_model=list[EmpresaResponse],
    dependencies=[Depends(usuario_actual)],
    summary="Listar empresas",
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

    # `correos_notificacion: null` es "no la toques"; `[]` la vacía.
    if cambios.get("correos_notificacion", []) is None:
        cambios.pop("correos_notificacion")

    # Un client_id/secret vacío significa "no lo toques", no "bórralo".
    for campo in ("sunat_client_id", "sunat_client_secret"):
        if campo in cambios and not cambios[campo]:
            cambios.pop(campo)

    # La actividad elegida para clasificar tiene que ser una de las suyas.
    principal = cambios.get("ciiu_principal_clasificacion")
    actividades = cambios.get("actividades_economicas", empresa.get("actividades_economicas"))
    if principal and not any(a.get("ciiu") == principal for a in actividades or []):
        raise HTTPException(
            status_code=422,
            detail="La actividad principal para clasificar debe estar entre sus actividades",
        )

    actualizada = await repo_empresas.actualizar(db, empresa["_id"], cambios)
    return _con_rubro(actualizada)


@router.delete("/{ruc}", response_model=MessageResponse, summary="Eliminar empresa")
async def eliminar_empresa(empresa: dict = Depends(empresa_actual), db=Depends(get_db)):
    empresa_id = str(empresa["_id"])

    await repo_comprobantes.eliminar_de_empresa(db, empresa_id)
    await repo_periodos.eliminar_de_empresa(db, empresa_id)
    await repo_plan_cuentas.eliminar_de_empresa(db, empresa_id)
    await repo_comprobantes_externos.eliminar_de_empresa(db, empresa_id)
    await repo_codigos_vinculacion.eliminar_de_empresa(db, empresa_id)
    await repo_frecuentes.eliminar_de_empresa(db, empresa_id)
    imagenes_externas.eliminar_de_empresa(empresa_id)

    if await repo_empresas.eliminar(db, empresa["_id"]) == 0:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    return {"mensaje": "Empresa y datos asociados eliminados"}


@router.post(
    "/{ruc}/ficha-ruc",
    response_model=EmpresaResponse,
    summary="Obtener CIIU de la empresa desde la Consulta RUC de SUNAT",
)
@limiter.limit("10/minute")
async def obtener_ciiu_empresa(
    request: Request, empresa: dict = Depends(empresa_actual), db=Depends(get_db)
):
    """Consulta la ficha RUC pública de la empresa y guarda sus actividades
    económicas (CIIU), que el clasificador contable usa como contexto.
    Reemplaza las actividades que hubiera."""
    try:
        actualizada = await ficha_ruc_service.actualizar_empresa(db, empresa)
    except FichaNoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Consulta RUC fallida ruc=%s", empresa["ruc"])
        raise HTTPException(
            status_code=502, detail=f"No se pudo consultar la ficha RUC en SUNAT: {exc}"
        ) from exc
    return _con_rubro(actualizada)


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


class CredencialesSunatResultado(BaseModel):
    origen: Literal["existente", "creada"]
    aplicacion: str
    client_id: str
    token_valido: bool
    mensaje: str


@router.post(
    "/{ruc}/credenciales-sunat",
    response_model=CredencialesSunatResultado,
    summary="Obtener de SUNAT el client_id y la clave del API (o registrarlos)",
)
@limiter.limit("3/minute")
async def obtener_credenciales_sunat(
    request: Request,
    crear: bool = True,
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    """Con el usuario y la clave SOL guardados entra a «Credenciales de API SUNAT».

    Usa la aplicación que la empresa ya tenga; si no tiene y `crear` es verdadero
    registra una con acceso a SIRE. Guarda el client_id y la clave en la empresa
    y nunca devuelve la clave. Tarda lo que un inicio de sesión SOL (≈30-60 s).
    """
    try:
        return await credenciales_sunat_service.obtener(db, empresa, crear=crear)
    except CredencialesSolError:
        raise HTTPException(
            status_code=400, detail="SUNAT rechazó el usuario o la clave SOL de la empresa"
        ) from None
    except SinRecursoSire as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except (SesionSolError, CredencialesApiError) as exc:
        logger.warning("Credenciales SUNAT fallidas ruc=%s: %s", empresa["ruc"], exc)
        raise HTTPException(
            status_code=502, detail=f"No se pudieron obtener las credenciales de SUNAT: {exc}"
        ) from None
