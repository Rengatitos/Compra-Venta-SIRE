"""Resumen de todas las empresas para el panel general."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import empresas as ruta
from app.core.auth import usuario_actual
from app.db.database import get_db
from app.domain.jobs import EstadoJob, Job, TipoJob
from app.services import resumen_empresas_service as servicio

ID_A, ID_B = ObjectId(), ObjectId()
CREDENCIALES = {"sunat_client_id": "id", "sunat_client_secret": "secreto"}
EMPRESAS = [
    {
        "_id": ID_B, "ruc": "20603391692", "nombre": "zeta sac",
        "correos_notificacion": ["z@x.pe"], **CREDENCIALES,
    },
    {"_id": ID_A, "ruc": "20610202251", "nombre": "Alfa SAC", **CREDENCIALES},
]
SIRE = datetime(2026, 9, 27, 10, tzinfo=UTC)


@pytest.fixture
def datos(monkeypatch):
    ultimo = Job(
        tipo=TipoJob.SINCRONIZACION_SIRE, ruc="20610202251", periodo="202608",
        estado=EstadoJob.COMPLETADO,
    )
    monkeypatch.setattr(servicio.repo_empresas, "listar", AsyncMock(return_value=EMPRESAS))
    monkeypatch.setattr(
        servicio.repo_jobs,
        "resumen_por_ruc",
        AsyncMock(return_value={
            "20610202251": {
                "ultimo": ultimo,
                "procesos_por_estado": {
                    "pendiente": 1, "en_progreso": 0, "completado": 3, "fallido": 1,
                },
                "ultima_actualizacion_sire": SIRE,
            }
        }),
    )
    monkeypatch.setattr(servicio.repo_cargas, "ultima_fila_por_ruc", AsyncMock(return_value={}))
    monkeypatch.setattr(
        servicio.repo_periodos,
        "listar_por_empresas",
        AsyncMock(return_value={
            str(ID_A): [{"periodo": "202608", "estado": "sincronizado"}],
        }),
    )


def test_agrega_periodos_procesos_y_ultima_descarga_sire(datos):
    resumen = asyncio.run(servicio.resumir(None))

    assert resumen["total_empresas"] == 2
    assert resumen["procesos_por_estado"] == {
        "pendiente": 1, "en_progreso": 0, "completado": 3, "fallido": 1,
    }
    alfa, zeta = resumen["empresas"]  # por nombre, sin distinguir mayúsculas
    assert alfa["ruc"] == "20610202251"
    assert alfa["total_periodos"] == 1
    assert alfa["ultima_actualizacion_sire"] == SIRE
    assert alfa["ultimo_proceso"]["tipo"] == "sincronizacion_sire"


def test_una_empresa_sin_actividad_sale_en_ceros(datos):
    zeta = asyncio.run(servicio.resumir(None))["empresas"][1]

    assert zeta["correos_notificacion"] == ["z@x.pe"]
    assert zeta["total_periodos"] == 0
    assert zeta["ultima_actualizacion_sire"] is None
    assert zeta["ultimo_proceso"] is None
    assert set(zeta["procesos_por_estado"].values()) == {0}


def test_la_ruta_del_resumen_no_choca_con_la_de_una_empresa(datos):
    app = FastAPI()
    app.state.limiter = ruta.limiter
    app.include_router(ruta.router, prefix="/empresas")
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[usuario_actual] = lambda: {"email": "a@b.pe", "rol": "admin"}

    r = TestClient(app).get("/empresas/resumen")

    assert r.status_code == 200
    assert r.json()["empresas"][0]["ultima_actualizacion_sire"].endswith("Z")


def test_con_credenciales_la_empresa_esta_lista():
    assert servicio.estado_alta(CREDENCIALES, None) == ("lista", None)


def test_mientras_la_cola_completa_su_alta_esta_registrando():
    fila = {"estado": "pendiente", "motivos": ["Completando los datos de SUNAT"]}
    assert servicio.estado_alta({}, fila) == ("registrando", None)


def test_sin_credenciales_requiere_correccion_con_el_motivo_del_alta():
    fila = {
        "estado": "agregada_con_observaciones",
        "motivos": [
            "Completando los datos de SUNAT (reintento 4 de 4)",
            "Error al obtener información de SUNAT: clave SOL rechazada",
        ],
    }
    estado, motivo = servicio.estado_alta({}, fila)
    assert estado == "requiere_correccion"
    assert motivo == "Error al obtener información de SUNAT: clave SOL rechazada"
    # Sin rastro de su alta, el motivo genérico.
    assert servicio.estado_alta({}, None) == ("requiere_correccion", servicio.SIN_CREDENCIALES)
