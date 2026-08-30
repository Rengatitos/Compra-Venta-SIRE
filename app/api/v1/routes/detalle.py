import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
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
    # El límite de slowapi es por IP y no impide encolar cinco extracciones
    # seguidas: cada una abriría su propio Chromium contra la misma sesión SOL.
    en_curso = await jobs_service.activo(
        db, empresa["ruc"], TipoJob.EXTRACCION_DETALLES
    )
    if en_curso:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya hay una extracción en curso para el periodo {en_curso.periodo}. "
                f"Espera a que termine (job {en_curso.job_id})."
            ),
        )

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
        # La plantilla se quedaba sin interpolar y el cliente recibía
        # "{job_id}" tal cual, que era lo que acababa mostrándose en el aviso.
        "mensaje": (
            f"Extracción iniciada. Consulta su avance en /api/v1/jobs/{job.job_id}"
        ),
    }
