import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.deps import empresa_actual, periodo_valido
from app.db.database import get_db
from app.domain.jobs import TipoJob
from app.schemas.job import JobAceptado
from app.services import detalle_service, jobs_service

router = APIRouter()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "",
    response_model=JobAceptado,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Extraer el detalle de los comprobantes desde SUNAT",
)
@limiter.limit("5/minute")
async def iniciar_extraccion(
    request: Request,
    background_tasks: BackgroundTasks,
    periodo: str = Depends(periodo_valido),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    job = await jobs_service.crear(
        db, TipoJob.EXTRACCION_DETALLES, empresa["ruc"], periodo
    )

    async def tarea(reportar):
        return await detalle_service.extraer(db, empresa, periodo, reportar)

    background_tasks.add_task(jobs_service.ejecutar, db, job.job_id, tarea)

    logger.info(
        "Extracción de detalle encolada ruc=%s periodo=%s job_id=%s",
        empresa["ruc"],
        periodo,
        job.job_id,
    )

    return {
        "job_id": job.job_id,
        "estado": job.estado.value,
        "mensaje": "Extracción iniciada. Consulta su avance en /api/v1/jobs/{job_id}",
    }
