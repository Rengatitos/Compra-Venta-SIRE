"""Ciclo de vida del motor de clasificación dentro de la API.

El motor pesa: carga torch, el modelo de embeddings y un índice de ~6000
fragmentos, y la primera vez tiene que calcular todos los embeddings. Por eso
se construye una sola vez por proceso, en un hilo, y la API arranca sin
esperarlo: `/health` y el resto de endpoints responden mientras tanto, y quien
pida una clasificación antes de que termine simplemente espera a que esté.

Un único worker de uvicorn (ver el Dockerfile) es lo que hace que "una vez por
proceso" sea "una vez".
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import settings as settings_api
from app.services.clasificador.config import Settings

logger = logging.getLogger(__name__)

DESHABILITADO = "deshabilitado"
SIN_INICIAR = "sin_iniciar"
CARGANDO = "cargando"
LISTO = "listo"
ERROR = "error"


class MotorNoDisponible(RuntimeError):
    """El clasificador está apagado o no pudo arrancar."""


class _Motor:
    def __init__(self) -> None:
        self.settings: Settings | None = None
        self.rag = None
        self.llm = None
        self.embedder = None
        self.clasificador = None
        self.estado = SIN_INICIAR
        self.error: str | None = None
        self._candado = threading.Lock()

    def iniciar(self) -> None:
        """Construye el motor. Bloquea; llamarlo desde un hilo."""
        with self._candado:
            if self.estado == LISTO:
                return
            self.estado = CARGANDO
            self.error = None
            try:
                # Importes aquí: con el clasificador apagado la API no paga
                # el coste de importar torch ni numpy.
                from app.services.clasificador.classifier import ClassifierService
                from app.services.clasificador.embeddings import MultilingualE5Embedder
                from app.services.clasificador.llm import GeminiGenerator
                from app.services.clasificador.rag import HybridRAG

                settings = Settings.from_env()
                settings.ensure_dirs()
                embedder = MultilingualE5Embedder(settings)
                embedder.load()
                rag = HybridRAG(settings, embedder)
                if settings.auto_index_on_startup:
                    logger.info("Índice del clasificador: %s", rag.update(force=False))
                llm = GeminiGenerator(settings)
                if settings.preload_llm:
                    llm.load()
                self.settings = settings
                self.embedder = embedder
                self.rag = rag
                self.llm = llm
                self.clasificador = ClassifierService(settings, rag, llm)
                self.estado = LISTO
                logger.info("Clasificador contable listo (modelo %s)", settings.gemini_model)
            except Exception as exc:
                logger.exception("No se pudo iniciar el clasificador contable")
                self.estado = ERROR
                self.error = str(exc)

    def reindexar(self, forzar: bool = False) -> dict[str, Any]:
        self.obtener()
        return self.rag.update(force=forzar)

    def obtener(self):
        if not settings_api.CLASIFICADOR_HABILITADO:
            raise MotorNoDisponible(
                "El clasificador contable está deshabilitado (CLASIFICADOR_HABILITADO=false)"
            )
        if self.estado != LISTO:
            self.iniciar()
        if self.estado != LISTO:
            raise MotorNoDisponible(f"El clasificador contable no pudo iniciar: {self.error}")
        return self.clasificador

    def describir(self) -> dict[str, Any]:
        estado = self.estado if settings_api.CLASIFICADOR_HABILITADO else DESHABILITADO
        manifiesto = getattr(self.rag, "manifest", None) or {}
        return {
            "estado": estado,
            "error": self.error,
            "modelo_llm": self.settings.gemini_model if self.settings else None,
            "llm_configurado": bool(getattr(self.llm, "loaded", False)),
            "modelo_embeddings": self.settings.embedding_model if self.settings else None,
            "fragmentos_indexados": len(getattr(self.rag, "chunks", []) or []),
            "documentos_indexados": len(manifiesto.get("documents", {})),
            "backend_vectorial": getattr(self.rag, "backend", None),
        }


motor = _Motor()
