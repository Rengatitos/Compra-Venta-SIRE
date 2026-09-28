"""Cola durable: los trabajos viven en Mongo y el worker los toma de ahí.

Lo que se comprueba aquí es la política del worker: carriles (dos trabajos de
la misma empresa no se solapan), reintentos con espera creciente, errores que
no se reintentan, recuperación de lo que cortó un reinicio y el aviso al
orquestador cuando un paso de una solicitud queda cerrado. Mongo se sustituye
por un repositorio en memoria con la misma semántica que `app.repositories.jobs`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.jobs import EstadoJob, Job, TipoJob
from app.repositories import jobs as repo_jobs
from app.services.cola import errores, tareas, worker
from app.services.scraping_sunat import CredencialesSolError

RUC_A = "20610202251"
RUC_B = "20603391692"


class RepoFalso:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}

    def agregar(self, **campos) -> Job:
        base = {
            "tipo": TipoJob.EXTRACCION_DETALLES,
            "ruc": RUC_A,
            "periodo": "202608",
            "gestionado": True,
            "max_intentos": 3,
        }
        job = Job(**{**base, **campos})
        self.jobs[job.job_id] = job
        return job

    async def obtener(self, db, job_id):
        return self.jobs.get(job_id)

    async def tomar(self, db, ocupados, ahora):
        for job in sorted(self.jobs.values(), key=lambda j: j.creado_en):
            if not job.gestionado or job.estado is not EstadoJob.PENDIENTE:
                continue
            if job.siguiente_intento_en and job.siguiente_intento_en > ahora:
                continue
            if job.cola and job.cola in ocupados:
                continue
            job.estado = EstadoJob.EN_PROGRESO
            job.intentos += 1
            job.ultimo_intento_en = ahora
            job.latido_en = ahora
            return job.model_copy(deep=True)
        return None

    async def actualizar(self, db, job_id, *, progreso=None, **resto):
        if progreso is not None:
            self.jobs[job_id].progreso = progreso

    async def latir(self, db, job_id):
        self.jobs[job_id].latido_en = datetime.now(UTC)

    async def reprogramar(self, db, job_id, *, error, siguiente_intento_en, registro_error):
        job = self.jobs[job_id]
        job.estado = EstadoJob.PENDIENTE
        job.error = error
        job.siguiente_intento_en = siguiente_intento_en
        job.historial_errores.append(registro_error)

    async def finalizar(self, db, job_id, estado, *, resultado=None, error=None,
                        registro_error=None):
        job = self.jobs[job_id]
        job.estado = estado
        job.resultado = resultado
        job.error = error
        if registro_error:
            job.historial_errores.append(registro_error)


@pytest.fixture
def repo(monkeypatch):
    falso = RepoFalso()
    for nombre in ("obtener", "tomar", "actualizar", "latir", "reprogramar", "finalizar"):
        monkeypatch.setattr(worker.repo_jobs, nombre, getattr(falso, nombre))
    return falso


@pytest.fixture
def manejadores(monkeypatch):
    """Sustituye los manejadores reales por los que ponga cada test."""
    reemplazos: dict[TipoJob, object] = {}
    monkeypatch.setattr(tareas, "_MANEJADORES", reemplazos)
    return reemplazos


def test_un_trabajo_que_termina_queda_completado_con_su_resultado(repo, manejadores):
    manejadores[TipoJob.EXTRACCION_DETALLES] = AsyncMock(return_value={"procesados": 3})
    job = repo.agregar()

    hizo_algo = asyncio.run(worker.Worker(None).procesar_uno())

    assert hizo_algo
    assert repo.jobs[job.job_id].estado is EstadoJob.COMPLETADO
    assert repo.jobs[job.job_id].resultado == {"procesados": 3}


def test_sin_trabajos_no_hace_nada(repo, manejadores):
    assert asyncio.run(worker.Worker(None).procesar_uno()) is False


def test_un_fallo_pasajero_se_reintenta_con_espera_hasta_agotar_intentos(repo, manejadores):
    manejadores[TipoJob.EXTRACCION_DETALLES] = AsyncMock(side_effect=TimeoutError("SUNAT lento"))
    job = repo.agregar(max_intentos=2)
    trabajador = worker.Worker(None)

    antes = datetime.now(UTC)
    asyncio.run(trabajador.procesar_uno())
    primero = repo.jobs[job.job_id]
    assert primero.estado is EstadoJob.PENDIENTE
    assert primero.intentos == 1
    assert primero.siguiente_intento_en >= antes + timedelta(seconds=25)
    assert primero.historial_errores[0]["error"] == "SUNAT lento"

    # Antes de su hora no se vuelve a tomar.
    assert asyncio.run(trabajador.procesar_uno()) is False

    primero.siguiente_intento_en = datetime.now(UTC) - timedelta(seconds=1)
    asyncio.run(trabajador.procesar_uno())
    final = repo.jobs[job.job_id]
    assert final.estado is EstadoJob.FALLIDO
    assert final.intentos == 2
    assert len(final.historial_errores) == 2


@pytest.mark.parametrize(
    "fallo",
    [
        errores.ErrorPermanente("La empresa ya no existe"),
        CredencialesSolError("Usuario o Clave Incorrectos"),
    ],
)
def test_un_error_permanente_no_se_reintenta(repo, manejadores, fallo):
    manejadores[TipoJob.EXTRACCION_DETALLES] = AsyncMock(side_effect=fallo)
    job = repo.agregar(max_intentos=5)

    asyncio.run(worker.Worker(None).procesar_uno())

    assert repo.jobs[job.job_id].estado is EstadoJob.FALLIDO
    assert repo.jobs[job.job_id].intentos == 1


def test_un_tipo_sin_manejador_falla_sin_reintento(repo, manejadores):
    job = repo.agregar(tipo=TipoJob.DETRACCIONES, max_intentos=5)

    asyncio.run(worker.Worker(None).procesar_uno())

    assert repo.jobs[job.job_id].estado is EstadoJob.FALLIDO
    assert "manejador" in repo.jobs[job.job_id].error


def test_dos_trabajos_del_mismo_carril_no_se_solapan(repo, manejadores):
    dentro = 0
    maximo = 0

    async def lento(db, job, reportar):
        nonlocal dentro, maximo
        dentro += 1
        maximo = max(maximo, dentro)
        await asyncio.sleep(0.02)
        dentro -= 1
        return {}

    manejadores[TipoJob.EXTRACCION_DETALLES] = lento
    repo.agregar(cola=RUC_A, libro="compras")
    repo.agregar(cola=RUC_A, libro="ventas")
    trabajador = worker.Worker(None)

    async def principal():
        # Dos trabajadores a la vez: el segundo no encuentra nada libre.
        return await asyncio.gather(trabajador.procesar_uno(), trabajador.procesar_uno())

    tomados = asyncio.run(principal())

    assert maximo == 1
    assert sorted(tomados) == [False, True]
    assert asyncio.run(trabajador.procesar_uno()) is True
    assert all(j.estado is EstadoJob.COMPLETADO for j in repo.jobs.values())


def test_carriles_distintos_corren_a_la_vez(repo, manejadores):
    dentro = 0
    maximo = 0

    async def lento(db, job, reportar):
        nonlocal dentro, maximo
        dentro += 1
        maximo = max(maximo, dentro)
        await asyncio.sleep(0.02)
        dentro -= 1
        return {}

    manejadores[TipoJob.EXTRACCION_DETALLES] = lento
    repo.agregar(cola=RUC_A)
    repo.agregar(cola=RUC_B, ruc=RUC_B)
    trabajador = worker.Worker(None)

    async def principal():
        return await asyncio.gather(trabajador.procesar_uno(), trabajador.procesar_uno())

    assert asyncio.run(principal()) == [True, True]
    assert maximo == 2


def test_un_fallo_libera_el_carril(repo, manejadores):
    llamadas = []

    async def manejador(db, job, reportar):
        llamadas.append(job.libro)
        if job.libro.value == "compras":
            raise errores.ErrorPermanente("roto")
        return {}

    manejadores[TipoJob.EXTRACCION_DETALLES] = manejador
    repo.agregar(cola=RUC_A, libro="compras")
    repo.agregar(cola=RUC_A, libro="ventas")
    trabajador = worker.Worker(None)

    asyncio.run(trabajador.procesar_uno())
    asyncio.run(trabajador.procesar_uno())

    assert len(llamadas) == 2
    assert trabajador._ocupados == set()


def test_avisa_al_orquestador_solo_cuando_el_paso_queda_cerrado(repo, manejadores):
    manejadores[TipoJob.EXTRACCION_DETALLES] = AsyncMock(side_effect=[OSError("red"), {}])
    avisos: list[str] = []

    async def al_terminar(db, job):
        avisos.append(job.estado.value)

    job = repo.agregar(solicitud_id="s1")
    trabajador = worker.Worker(None, al_terminar=al_terminar)

    asyncio.run(trabajador.procesar_uno())
    assert avisos == []  # reprogramado: el paso sigue abierto

    repo.jobs[job.job_id].siguiente_intento_en = None
    asyncio.run(trabajador.procesar_uno())
    assert avisos == ["completado"]


def test_sin_solicitud_no_se_avisa(repo, manejadores):
    manejadores[TipoJob.EXTRACCION_DETALLES] = AsyncMock(return_value={})
    al_terminar = AsyncMock()
    repo.agregar()

    asyncio.run(worker.Worker(None, al_terminar=al_terminar).procesar_uno())

    al_terminar.assert_not_awaited()


def test_la_espera_crece_y_tiene_techo(monkeypatch):
    monkeypatch.setattr(worker.settings, "COLA_BACKOFF_BASE_S", 30)
    monkeypatch.setattr(worker.settings, "COLA_BACKOFF_MAX_S", 1800)
    esperas = [worker.espera_reintento(n).total_seconds() for n in (1, 2, 3, 10)]
    assert esperas == [30, 60, 120, 1800]


# --- Consultas a Mongo ------------------------------------------------------


class ColeccionEspia:
    def __init__(self) -> None:
        self.llamadas: list[tuple[str, tuple, dict]] = []

    async def find_one_and_update(self, *args, **kwargs):
        self.llamadas.append(("find_one_and_update", args, kwargs))
        return None

    async def update_many(self, *args, **kwargs):
        self.llamadas.append(("update_many", args, kwargs))
        return SimpleNamespace(modified_count=0)


@pytest.fixture
def coleccion(monkeypatch):
    espia = ColeccionEspia()
    monkeypatch.setattr(repo_jobs, "_col", lambda db: espia)
    return espia


def test_tomar_solo_mira_los_gestionados_y_salta_los_carriles_ocupados(coleccion):
    asyncio.run(repo_jobs.tomar(None, {RUC_A}, datetime.now(UTC)))

    _, (filtro, cambios), opciones = coleccion.llamadas[0]
    assert filtro["gestionado"] is True
    assert filtro["estado"] == "pendiente"
    assert filtro["cola"] == {"$nin": [RUC_A]}
    assert cambios["$inc"] == {"intentos": 1}
    assert opciones["sort"] == [("creado_en", 1)]


def test_la_recuperacion_no_toca_los_jobs_de_otra_copia_de_la_api(coleccion):
    asyncio.run(repo_jobs.recuperar_huerfanos(None, datetime.now(UTC)))

    for _, (filtro, _cambios), _ in coleccion.llamadas:
        assert filtro["gestionado"] is True
        assert filtro["estado"] == "en_progreso"


def test_al_arrancar_no_se_dan_por_fallidos_los_de_la_cola(coleccion):
    asyncio.run(repo_jobs.marcar_interrumpidos(None, [TipoJob.CLASIFICACION_CUENTAS]))

    _, (filtro, _), _ = coleccion.llamadas[0]
    assert filtro["gestionado"] == {"$ne": True}


# --- Manejadores ------------------------------------------------------------


def test_la_extraccion_de_una_solicitud_sigue_hasta_terminar(monkeypatch):
    from app.services import detalle_service

    rondas = [
        {"procesados": 100, "con_detalle": 90, "pendientes": 30},
        {"procesados": 30, "con_detalle": 30, "pendientes": 0},
    ]
    extraer = AsyncMock(side_effect=rondas)
    monkeypatch.setattr(detalle_service, "extraer", extraer)
    empresa = AsyncMock(return_value={"ruc": RUC_A})
    monkeypatch.setattr(tareas.repo_empresas, "obtener_por_ruc", empresa)
    job = Job(
        tipo=TipoJob.EXTRACCION_DETALLES, ruc=RUC_A, periodo="202608", libro="compras",
        parametros={"hasta_terminar": True},
    )

    resultado = asyncio.run(tareas.extraccion_detalles(None, job, AsyncMock()))

    assert extraer.await_count == 2
    assert resultado["procesados"] == 130
    assert resultado["pendientes"] == 0
    assert resultado["rondas"] == 2


def test_una_empresa_borrada_es_un_error_permanente(monkeypatch):
    monkeypatch.setattr(tareas.repo_empresas, "obtener_por_ruc", AsyncMock(return_value=None))
    job = Job(tipo=TipoJob.DETRACCIONES, ruc=RUC_A, periodo="202608")

    with pytest.raises(errores.ErrorPermanente):
        asyncio.run(tareas.detracciones(None, job, AsyncMock()))
