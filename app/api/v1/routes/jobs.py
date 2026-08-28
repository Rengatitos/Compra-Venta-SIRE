from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import empresa_autenticada
from app.db.database import get_db
from app.schemas.job import JobResponse
from app.services import jobs_service

router = APIRouter()


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
