import asyncio
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual, libro_valido, periodo_valido
from app.core.auth import usuario_actual
from app.core.config import settings
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.domain.jobs import TipoJob
from app.schemas.job import JobAceptado
from app.services import clasificacion_service, jobs_service
from app.services.clasificador.motor import MotorNoDisponible, motor

router = APIRouter()
# Estado y mantenimiento del motor: no dependen de ninguna empresa.
router_motor = APIRouter(dependencies=[Depends(usuario_actual)])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

# Una sola cola para todas las empresas: el motor es uno por proceso y serializa
# sus llamadas a Gemini, así que dos lotes en paralelo sólo se estorbarían.
COLA = "clasificador"


def exigir_habilitado() -> None:
    if not settings.CLASIFICADOR_HABILITADO:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El clasificador contable está deshabilitado (CLASIFICADOR_HABILITADO)",
        )


@router.post(
    "",
    response_model=JobAceptado,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Clasificar las cuentas contables de los comprobantes del libro",
    dependencies=[Depends(exigir_habilitado)],
)
@limiter.limit("5/minute")
async def iniciar_clasificacion(
    request: Request,
    background_tasks: BackgroundTasks,
    reclasificar: bool = Query(
        False, description="Vuelve a clasificar también los que ya tienen clasificación"
    ),
    periodo: str = Depends(periodo_valido),
    libro: Libro = Depends(libro_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    duplicado = await jobs_service.activo(
        db, empresa["ruc"], TipoJob.CLASIFICACION_CUENTAS, periodo=periodo, libro=libro
    )
    if duplicado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya hay una clasificación de {libro.value} en curso para el periodo "
                f"{periodo} (job {duplicado.job_id})."
            ),
        )

    job = await jobs_service.crear(
        db, TipoJob.CLASIFICACION_CUENTAS, empresa["ruc"], periodo, libro
    )

    async def tarea(reportar):
        return await clasificacion_service.clasificar_periodo(
            db, empresa, periodo, libro, reportar, reclasificar=reclasificar
        )

    background_tasks.add_task(jobs_service.ejecutar, db, job.job_id, tarea, COLA)
    logger.info(
        "Clasificación encolada ruc=%s periodo=%s libro=%s job_id=%s",
        empresa["ruc"], periodo, libro.value, job.job_id,
    )
    return {
        "job_id": job.job_id,
        "estado": job.estado.value,
        "mensaje": (
            f"Clasificación de {libro.value} iniciada. "
            f"Consulta su avance en /api/v1/jobs/{job.job_id}"
        ),
    }


@router_motor.get("/estado", summary="Estado del clasificador contable")
async def estado():
    return clasificacion_service.estado_motor()


@router_motor.post(
    "/reindexar",
    summary="Actualizar el índice del clasificador",
    dependencies=[Depends(exigir_habilitado)],
)
@limiter.limit("2/minute")
async def reindexar(request: Request, forzar: bool = Query(False)):
    """Recalcula los embeddings de los documentos de conocimiento nuevos o
    modificados (con `forzar`, de todos)."""
    try:
        return await asyncio.to_thread(motor.reindexar, forzar)
    except MotorNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
