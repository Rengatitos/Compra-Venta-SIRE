"""El worker de la cola durable: toma trabajos de Mongo y los ejecuta.

Corre dentro de la API como `COLA_TRABAJADORES` corrutinas. Cada una:

1. Toma el pendiente más antiguo cuyo carril esté libre (`repo_jobs.tomar`,
   atómico), lo marca en progreso y aparta su carril.
2. Ejecuta el manejador de su tipo (`app.services.cola.tareas`) mientras
   actualiza su latido.
3. Si termina, lo cierra como completado. Si falla por algo permanente, como
   fallido. Si falla por algo pasajero y le quedan intentos, lo devuelve a la
   cola con una espera que crece en cada intento.
4. Si el trabajo es un paso de una solicitud y ya no se va a reintentar, avisa
   al orquestador para que encadene el paso siguiente.

Aparte, cada minuto vuelve a la cola los trabajos cuyo latido venció: son los
que estaban en curso cuando la API se reinició.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.domain.jobs import EstadoJob, Job, Progreso
from app.repositories import jobs as repo_jobs
from app.services.cola.errores import ErrorPermanente

logger = logging.getLogger(__name__)

# Se llama con el job ya cerrado (completado o fallido sin más intentos).
AlTerminar = Callable[[AsyncIOMotorDatabase, Job], Awaitable[None]]

INTERVALO_RECUPERACION_S = 60
MAX_ERROR = 2000


def espera_reintento(intentos: int) -> timedelta:
    """Cuánto esperar antes del siguiente intento, tras `intentos` fallidos."""
    segundos = settings.COLA_BACKOFF_BASE_S * 2 ** max(intentos - 1, 0)
    return timedelta(seconds=min(segundos, settings.COLA_BACKOFF_MAX_S))


def es_permanente(exc: BaseException) -> bool:
    if isinstance(exc, ErrorPermanente):
        return True
    # Importados aquí para no cargar Playwright al importar la cola.
    from app.services.scraping_sunat import CredencialesSolError
    from app.services.sunat.credenciales_api import SinRecursoSire

    # Una clave SOL rechazada no se arregla sola, y reintentarla puede
    # bloquear el usuario en SUNAT.
    return isinstance(exc, CredencialesSolError | SinRecursoSire)


class Worker:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        *,
        trabajadores: int | None = None,
        al_terminar: AlTerminar | None = None,
    ) -> None:
        self.db = db
        self.trabajadores = trabajadores or settings.COLA_TRABAJADORES
        self._al_terminar = al_terminar
        self._ocupados: set[str] = set()
        self._toma = asyncio.Lock()
        self._despertar = asyncio.Event()
        self._tareas: list[asyncio.Task] = []
        self._detenido = False

    # --- Ciclo de vida -----------------------------------------------------

    def arrancar(self) -> None:
        self._detenido = False
        self._tareas = [
            asyncio.create_task(self._bucle(i), name=f"cola-{i}")
            for i in range(self.trabajadores)
        ]
        self._tareas.append(asyncio.create_task(self._vigilar(), name="cola-vigilancia"))
        logger.info("Cola durable en marcha con %s trabajadores", self.trabajadores)

    async def detener(self) -> None:
        self._detenido = True
        for tarea in self._tareas:
            tarea.cancel()
        for tarea in self._tareas:
            with contextlib.suppress(asyncio.CancelledError):
                await tarea
        self._tareas = []

    def despertar(self) -> None:
        self._despertar.set()

    # --- Bucle -------------------------------------------------------------

    async def _bucle(self, numero: int) -> None:
        while not self._detenido:
            try:
                hizo_algo = await self.procesar_uno()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Un fallo de Mongo no debe matar al trabajador: se reintenta
                # en la siguiente vuelta.
                logger.exception("Error en el trabajador %s de la cola", numero)
                hizo_algo = False
            if hizo_algo:
                continue
            self._despertar.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._despertar.wait(), settings.COLA_INTERVALO_S)

    async def _vigilar(self) -> None:
        while not self._detenido:
            try:
                await self.recuperar()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("No se pudieron recuperar los trabajos huérfanos")
            await asyncio.sleep(INTERVALO_RECUPERACION_S)

    async def recuperar(self) -> int:
        limite = datetime.now(UTC) - timedelta(seconds=settings.COLA_LATIDO_VENCIDO_S)
        recuperados = await repo_jobs.recuperar_huerfanos(self.db, limite)
        if recuperados:
            logger.warning("%s trabajos interrumpidos vuelven a la cola", recuperados)
            self.despertar()
        return recuperados

    async def procesar_uno(self) -> bool:
        """Toma y ejecuta un trabajo. Devuelve si había alguno."""
        # La toma se serializa entre trabajadores: sin el candado dos podrían
        # leer los mismos carriles libres y llevarse dos jobs del mismo RUC.
        async with self._toma:
            job = await repo_jobs.tomar(self.db, self._ocupados, datetime.now(UTC))
            if job is None:
                return False
            if job.cola:
                self._ocupados.add(job.cola)
        try:
            await self._ejecutar(job)
        finally:
            if job.cola:
                self._ocupados.discard(job.cola)
            # Liberar un carril puede destrabar a otro trabajo que esperaba.
            self.despertar()
        return True

    # --- Ejecución ---------------------------------------------------------

    async def _ejecutar(self, job: Job) -> None:
        from app.services.cola import tareas

        async def reportar(actual: int, total: int, mensaje: str = "") -> None:
            await repo_jobs.actualizar(
                self.db,
                job.job_id,
                progreso=Progreso(actual=actual, total=total, mensaje=mensaje),
            )

        latido = asyncio.create_task(self._latir(job.job_id))
        logger.info(
            "Job %s (%s ruc=%s periodo=%s) intento %s/%s",
            job.job_id, job.tipo.value, job.ruc, job.periodo, job.intentos, job.max_intentos,
        )
        try:
            manejador = tareas.manejador(job.tipo)
            resultado = await manejador(self.db, job, reportar)
        except asyncio.CancelledError:
            # Apagado de la API: el job queda en progreso con el latido viejo
            # y la recuperación lo devuelve a la cola al volver a arrancar.
            raise
        except Exception as exc:
            await self._fallo(job, exc)
        else:
            await repo_jobs.finalizar(
                self.db, job.job_id, EstadoJob.COMPLETADO, resultado=resultado or {}
            )
            logger.info("Job %s completado", job.job_id)
            await self._terminado(job.job_id)
        finally:
            latido.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await latido

    async def _fallo(self, job: Job, exc: Exception) -> None:
        ahora = datetime.now(UTC)
        error = (str(exc) or type(exc).__name__)[:MAX_ERROR]
        registro = {"intento": job.intentos, "en": ahora, "error": error}
        permanente = es_permanente(exc)
        if not permanente and job.intentos < job.max_intentos:
            siguiente = ahora + espera_reintento(job.intentos)
            await repo_jobs.reprogramar(
                self.db,
                job.job_id,
                error=error,
                siguiente_intento_en=siguiente,
                registro_error=registro,
            )
            logger.warning(
                "Job %s falló (intento %s/%s), se reintenta a las %s: %s",
                job.job_id, job.intentos, job.max_intentos, siguiente.isoformat(), error,
            )
            return
        await repo_jobs.finalizar(
            self.db, job.job_id, EstadoJob.FALLIDO, error=error, registro_error=registro
        )
        if permanente:
            logger.warning("Job %s fallido sin reintento: %s", job.job_id, error)
        else:
            logger.exception("Job %s fallido tras %s intentos", job.job_id, job.intentos)
        await self._terminado(job.job_id)

    async def _terminado(self, job_id: str) -> None:
        if self._al_terminar is None:
            return
        job = await repo_jobs.obtener(self.db, job_id)
        if job is None or not job.solicitud_id:
            return
        try:
            await self._al_terminar(self.db, job)
        except Exception:
            # El paso ya quedó cerrado; un fallo al encadenar el siguiente se
            # registra y la solicitud se puede reanudar con «Reintentar».
            logger.exception("No se pudo encadenar el paso siguiente del job %s", job_id)

    async def _latir(self, job_id: str) -> None:
        while True:
            await asyncio.sleep(settings.COLA_LATIDO_S)
            try:
                await repo_jobs.latir(self.db, job_id)
            except Exception:
                logger.exception("No se pudo registrar el latido del job %s", job_id)


# El worker del proceso. Lo crea el `lifespan` de la API; `encolar` lo despierta
# para que un trabajo nuevo no espere a la siguiente vuelta.
_actual: Worker | None = None


def instalar(worker: Worker | None) -> None:
    global _actual
    _actual = worker


def despertar() -> None:
    if _actual is not None:
        _actual.despertar()


async def al_terminar_solicitud(db: AsyncIOMotorDatabase, job: Job) -> None:
    """Enlace con el orquestador de solicitudes, importado al usarse porque
    ese módulo encola trabajos y, con ello, importa esta cola."""
    from app.services import solicitudes_service

    await solicitudes_service.al_terminar(db, job)
