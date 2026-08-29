from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import empresa_autenticada
from app.db.database import get_db
from app.domain.jobs import EstadoJob, TipoJob
from app.schemas.job import JobResponse
from app.services import jobs_service

router = APIRouter()


@router.get("", response_model=list[JobResponse], summary="Listar trabajos de la empresa")
async def listar_jobs(
    periodo: str | None = Query(None, description="Filtra por periodo YYYYMM"),
    tipo: TipoJob | None = Query(None, description="Filtra por tipo de trabajo"),
    estado: EstadoJob | None = Query(None, description="Filtra por estado"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    empresa: dict = Depends(empresa_autenticada),
    db=Depends(get_db),
):
    # El RUC sale del token, nunca de un query param: así el historial no puede
    # apuntar a otra empresa aunque el cliente lo pida.
    jobs = await jobs_service.listar(
        db,
        empresa.get("ruc"),
        periodo=periodo,
        tipo=tipo,
        estado=estado,
        limit=limit,
        skip=skip,
    )
    return [jobs_service.serializar(job) for job in jobs]


@router.get("/{job_id}", response_model=JobResponse, summary="Consultar un trabajo")
async def obtener_job(
    job_id: str,
    empresa: dict = Depends(empresa_autenticada),
    db=Depends(get_db),
):
    job = await jobs_service.obtener(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")

    # El job no está anidado bajo /empresas/{ruc}, así que la pertenencia se
    # comprueba aquí contra el RUC del token.
    if job.ruc != empresa.get("ruc"):
        raise HTTPException(status_code=403, detail="El trabajo pertenece a otra empresa")

    return jobs_service.serializar(job)
