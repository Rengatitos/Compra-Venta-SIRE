"""Los trabajos de una empresa se serializan en vez de rechazarse.

El scraper abre un Chromium y entra con la sesión SOL, que es única por
usuario: dos extracciones a la vez se pelean por ella. Antes eso se resolvía
con un `409` que obligaba al usuario a estar pendiente de cuándo terminaba una
para lanzar la otra. Ahora la segunda se acepta y espera su turno.
"""

from __future__ import annotations

import asyncio

from app.domain.jobs import EstadoJob
from app.services import jobs_service


class RepoFalso:
    """Sustituye a `repo_jobs`: sólo hace falta recordar estados y progreso."""

    def __init__(self) -> None:
        self.estados: dict[str, list[EstadoJob]] = {}
        self.mensajes: dict[str, list[str]] = {}

    async def actualizar(self, db, job_id, *, estado=None, progreso=None, **resto):
        if estado is not None:
            self.estados.setdefault(job_id, []).append(estado)
        if progreso is not None and progreso.mensaje:
            self.mensajes.setdefault(job_id, []).append(progreso.mensaje)


def _preparar(monkeypatch) -> RepoFalso:
    repo = RepoFalso()
    monkeypatch.setattr(jobs_service, "repo_jobs", repo)
    # Cada test arranca con las colas limpias.
    jobs_service._colas.clear()
    return repo


def test_dos_trabajos_de_la_misma_empresa_no_se_solapan(monkeypatch):
    repo = _preparar(monkeypatch)
    dentro = 0
    solapes = 0

    def tarea(nombre):
        async def correr(reportar):
            nonlocal dentro, solapes
            dentro += 1
            if dentro > 1:
                solapes += 1
            # Cede el control: si no hubiera cola, el otro entraría aquí.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            dentro -= 1
            return {"quien": nombre}
        return correr

    async def principal():
        await asyncio.gather(
            jobs_service.ejecutar(None, "compras", tarea("compras"), "20610202251"),
            jobs_service.ejecutar(None, "ventas", tarea("ventas"), "20610202251"),
        )

    asyncio.run(principal())

    assert solapes == 0
    assert repo.estados["compras"][-1] is EstadoJob.COMPLETADO
    assert repo.estados["ventas"][-1] is EstadoJob.COMPLETADO


def test_el_segundo_avisa_de_que_esta_en_cola(monkeypatch):
    # Sin este aviso el trabajo parece colgado en `pendiente` sin explicación.
    repo = _preparar(monkeypatch)

    async def lenta(reportar):
        await asyncio.sleep(0.05)
        return {}

    async def rapida(reportar):
        return {}

    async def principal():
        primera = asyncio.create_task(
            jobs_service.ejecutar(None, "primera", lenta, "20610202251")
        )
        await asyncio.sleep(0)  # deja que la primera tome el candado
        await jobs_service.ejecutar(None, "segunda", rapida, "20610202251")
        await primera

    asyncio.run(principal())

    assert any("cola" in m.lower() for m in repo.mensajes.get("segunda", []))
    assert "primera" not in repo.mensajes


def test_empresas_distintas_no_se_esperan(monkeypatch):
    _preparar(monkeypatch)
    orden: list[str] = []

    def tarea(nombre, espera):
        async def correr(reportar):
            await asyncio.sleep(espera)
            orden.append(nombre)
            return {}
        return correr

    async def principal():
        await asyncio.gather(
            jobs_service.ejecutar(None, "a", tarea("lenta", 0.05), "20610202251"),
            jobs_service.ejecutar(None, "b", tarea("rapida", 0.0), "20603391692"),
        )

    asyncio.run(principal())

    # La rápida de otra empresa no espera a la lenta.
    assert orden == ["rapida", "lenta"]


def test_un_fallo_libera_la_cola(monkeypatch):
    # Si una excepción dejara el candado tomado, la empresa no podría volver a
    # extraer nada hasta reiniciar el proceso.
    repo = _preparar(monkeypatch)

    async def revienta(reportar):
        raise RuntimeError("el portal se cayó")

    async def sana(reportar):
        return {}

    async def principal():
        await jobs_service.ejecutar(None, "rota", revienta, "20610202251")
        await jobs_service.ejecutar(None, "siguiente", sana, "20610202251")

    asyncio.run(principal())

    assert repo.estados["rota"][-1] is EstadoJob.FALLIDO
    assert repo.estados["siguiente"][-1] is EstadoJob.COMPLETADO
    assert not jobs_service._cola("20610202251").locked()


def test_sin_cola_el_trabajo_corre_directo(monkeypatch):
    repo = _preparar(monkeypatch)

    async def tarea(reportar):
        return {"ok": True}

    asyncio.run(jobs_service.ejecutar(None, "suelto", tarea))

    assert repo.estados["suelto"] == [EstadoJob.EN_PROGRESO, EstadoJob.COMPLETADO]
