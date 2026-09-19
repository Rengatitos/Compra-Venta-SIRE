from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import usuario_actual
from app.db.database import get_db
from app.domain.jobs import EstadoJob, TipoJob
from app.repositories import empresas as repo_empresas
from app.schemas.job import JobResponse
from app.services import jobs_service

router = APIRouter()


@router.get("", response_model=list[JobResponse], summary="Listar trabajos")
async def listar_jobs(
    ruc: str | None = Query(None, description="Filtra por RUC; sin él, todas las empresas"),
    periodo: str | None = Query(None, description="Filtra por periodo YYYYMM"),
    tipo: TipoJob | None = Query(None, description="Filtra por tipo de trabajo"),
    estado: EstadoJob | None = Query(None, description="Filtra por estado"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    _usuario: dict = Depends(usuario_actual),
    db=Depends(get_db),
):
    # El RUC llegaba del token, porque el token identificaba a una empresa y
    # aceptarlo del cliente habría dejado pedir el historial de otra. Ahora el
    # token identifica a una persona con acceso a todas las empresas, así que el
    # parámetro ya no es una vía de escalada: no revela nada que la misma sesión
    # no pueda pedir por GET /empresas. Lo único que se comprueba de él es que
    # exista, para que un RUC mal escrito no se lea como "no hay trabajos".
    if ruc and not await repo_empresas.obtener_por_ruc(db, ruc):
        raise HTTPException(status_code=404, detail="No hay ninguna empresa con ese RUC")

    jobs = await jobs_service.listar(
        db,
        ruc,
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
    _usuario: dict = Depends(usuario_actual),
    db=Depends(get_db),
):
    # Aquí se comparaba `job.ruc` contra el RUC del token y se devolvía 403 si no
    # coincidían. Con una sesión por persona ya no hay "otra empresa" respecto de
    # la cual un trabajo sea ajeno, así que solo queda el 404.
    job = await jobs_service.obtener(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")

    return jobs_service.serializar(job)
