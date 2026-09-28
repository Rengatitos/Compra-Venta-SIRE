"""Cada descarga SIRE deja un job `sincronizacion_sire` en el historial."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from app.domain.comprobante import Libro
from app.domain.jobs import EstadoJob, Job, TipoJob
from app.services import propuesta_service as servicio
from app.services.cola import errores, tareas
from app.services.sunat.auth import ErrorSunat

RUC = "20610202251"
EMPRESA = {"_id": ObjectId(), "ruc": RUC, "sunat_client_id": "id", "sunat_client_secret": "s"}


class RepoJobs:
    def __init__(self) -> None:
        self.creados: list[Job] = []
        self.cambios: list[dict] = []

    async def crear(self, db, job):
        self.creados.append(job)
        return job

    async def actualizar(self, db, job_id, **cambios):
        self.cambios.append(cambios)


@pytest.fixture
def jobs(monkeypatch):
    repo = RepoJobs()
    monkeypatch.setattr(servicio.repo_jobs, "crear", repo.crear)
    monkeypatch.setattr(servicio.repo_jobs, "actualizar", repo.actualizar)
    return repo


def test_una_descarga_exitosa_queda_como_job_completado(monkeypatch, jobs):
    resultado = {"nuevos": 2, "actualizados": 1, "descartados": 0, "mensaje": "OK"}
    monkeypatch.setattr(servicio, "descargar_propuesta", AsyncMock(return_value=resultado))

    asyncio.run(servicio.sincronizar(None, EMPRESA, "202608", Libro.VENTAS))

    [job] = jobs.creados
    assert job.tipo is TipoJob.SINCRONIZACION_SIRE
    assert job.estado is EstadoJob.EN_PROGRESO
    assert job.libro is Libro.VENTAS
    assert not job.gestionado  # historial: la cola no lo ejecuta
    final = jobs.cambios[-1]
    assert final["estado"] is EstadoJob.COMPLETADO
    assert final["resultado"]["origen"] == "propuesta"
    assert final["resultado"]["nuevos"] == 2


def test_un_error_de_sunat_queda_fallido_y_se_relanza(monkeypatch, jobs):
    monkeypatch.setattr(
        servicio, "descargar_propuesta", AsyncMock(side_effect=ErrorSunat("401"))
    )

    with pytest.raises(ErrorSunat):
        asyncio.run(servicio.sincronizar(None, EMPRESA, "202608", Libro.COMPRAS))

    assert jobs.cambios[-1]["estado"] is EstadoJob.FALLIDO
    assert "401" in jobs.cambios[-1]["error"]


def test_sin_propuesta_se_completa_con_la_marca(monkeypatch, jobs):
    monkeypatch.setattr(servicio.api_propuesta, "descargar", AsyncMock(return_value=None))
    monkeypatch.setattr(servicio.repo_periodos, "actualizar_estado", AsyncMock())

    resultado = asyncio.run(servicio.sincronizar(None, EMPRESA, "202608", Libro.COMPRAS))

    assert resultado["sin_propuesta"] is True
    assert jobs.cambios[-1]["resultado"]["sin_propuesta"] is True


def test_el_ticket_rce_registra_un_solo_job(monkeypatch, jobs):
    monkeypatch.setattr(servicio, "obtener_zip", AsyncMock(return_value=("T1", b"zip")))
    monkeypatch.setattr(
        servicio, "_importar_archivo_rce",
        AsyncMock(return_value={"filas_archivo": 3, "mensaje": "OK"}),
    )

    resultado = asyncio.run(servicio.sincronizar_ticket_rce(None, EMPRESA, "202608"))

    assert len(jobs.creados) == 1
    assert resultado["ticket"] == "T1"
    assert jobs.cambios[-1]["resultado"]["origen"] == "ticket_rce"


# --- El paso de la cola -----------------------------------------------------


def job_sire(libro="compras"):
    return Job(tipo=TipoJob.SINCRONIZACION_SIRE, ruc=RUC, periodo="202608", libro=libro)


def test_en_la_cola_no_crea_un_segundo_job_y_encadena_detracciones(monkeypatch, jobs):
    from app.services import detracciones_service

    monkeypatch.setattr(tareas.repo_empresas, "obtener_por_ruc", AsyncMock(return_value=EMPRESA))
    monkeypatch.setattr(
        servicio, "descargar_propuesta",
        AsyncMock(return_value={"nuevos": 1, "actualizados": 0, "mensaje": "OK"}),
    )
    encolar = AsyncMock(return_value=Job(tipo=TipoJob.DETRACCIONES, ruc=RUC, periodo="202608"))
    monkeypatch.setattr(detracciones_service, "encolar", encolar)

    resultado = asyncio.run(tareas.sincronizacion_sire(None, job_sire(), AsyncMock()))

    assert jobs.creados == []
    assert resultado["origen"] == "propuesta"
    encolar.assert_awaited_once()


def test_sin_credenciales_del_api_es_un_error_permanente(monkeypatch):
    sin_credenciales = {"_id": ObjectId(), "ruc": RUC}
    monkeypatch.setattr(
        tareas.repo_empresas, "obtener_por_ruc", AsyncMock(return_value=sin_credenciales)
    )
    monkeypatch.setattr("app.services.sunat.auth.settings.SUNAT_CLIENT_ID", None)
    monkeypatch.setattr("app.services.sunat.auth.settings.SUNAT_CLIENT_SECRET", None)

    with pytest.raises(errores.ErrorPermanente):
        asyncio.run(tareas.sincronizacion_sire(None, job_sire("ventas"), AsyncMock()))
