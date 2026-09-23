"""Configuración del motor de clasificación contable (RAG + Gemini).

Se lee del entorno y no de `app.core.config.settings` porque el motor se portó
tal cual desde su API independiente y sus ~30 parámetros de ajuste no pintan
nada en la configuración general. `load_dotenv` hace que el mismo `.env` de la
API sirva para ambos.

Rutas por defecto:

- El conocimiento (PCGE, plan CONTASIS, CIIU, normativa) va con el código, en
  `app/resources/clasificador/`, y entra a la imagen de Docker.
- El índice, la caché de embeddings y el modelo de Hugging Face se generan, así
  que van en `data/clasificador/`, que en Docker es un volumen: sin él, cada
  reinicio volvería a descargar el modelo y recalcular todos los embeddings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

RAIZ_REPO = Path(__file__).resolve().parents[3]
RECURSOS = RAIZ_REPO / "app" / "resources" / "clasificador"


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(slots=True)
class Settings:
    base_dir: Path
    knowledge_dir: Path
    index_dir: Path
    cache_dir: Path
    source_weights_path: Path

    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_api_key: str | None = None
    vertex_project: str = "project-577228a1-457d-489f-972"
    vertex_location: str = "global"
    google_application_credentials: str | None = None
    embedding_model: str = "intfloat/multilingual-e5-small"
    hf_home: str | None = None
    hf_token: str | None = None

    auto_index_on_startup: bool = True
    preload_llm: bool = True
    embedding_dynamic_int8: bool = True
    cpu_threads: int = 2

    embedding_batch_size: int = 12
    embedding_max_length: int = 384
    top_k_default: int = 3
    rag_candidate_pool: int = 15
    semantic_candidates: int = 30
    lexical_candidates: int = 30
    max_context_chars: int = 4000
    max_chunk_chars_in_prompt: int = 800

    semantic_weight: float = 0.65
    lexical_weight: float = 0.20
    metadata_weight: float = 0.15
    review_threshold: float = 0.60

    max_new_tokens: int = 800
    gemini_timeout_seconds: float = 30.0
    gemini_max_retries: int = 2
    # Google Search (grounding) en las etapas de interpretación. Nunca en la
    # elección final de cuentas, que sólo puede escoger entre candidatos del RAG.
    gemini_web_search: bool = True
    interpretation_enabled: bool = True
    final_selection_enabled: bool = True
    skip_heavy_startup: bool = False

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> Settings:
        root = (base_dir or RAIZ_REPO).resolve()
        recursos = RECURSOS if base_dir is None else root / "app" / "resources" / "clasificador"
        datos = root / "data" / "clasificador"
        knowledge = Path(os.getenv("KNOWLEDGE_DIR", recursos / "conocimiento")).resolve()
        index_dir = Path(os.getenv("RAG_INDEX_DIR", datos / "index")).resolve()
        cache_dir = Path(os.getenv("RAG_CACHE_DIR", datos / "cache")).resolve()
        source_weights = Path(os.getenv("RAG_SOURCE_WEIGHTS", recursos / "rag_sources.yaml")).resolve()
        return cls(
            base_dir=root,
            knowledge_dir=knowledge,
            index_dir=index_dir,
            cache_dir=cache_dir,
            source_weights_path=source_weights,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            vertex_project=os.getenv("VERTEX_PROJECT", "project-577228a1-457d-489f-972"),
            vertex_location=os.getenv("VERTEX_LOCATION", "global"),
            google_application_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", str(root / "service-account.json")),
            embedding_model=os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
            hf_home=os.getenv("HF_HOME", str(datos / "huggingface")),
            hf_token=os.getenv("HF_TOKEN"),
            auto_index_on_startup=_bool("AUTO_INDEX_ON_STARTUP", True),
            preload_llm=_bool("PRELOAD_LLM", True),
            embedding_dynamic_int8=_bool("EMBEDDING_DYNAMIC_INT8", True),
            cpu_threads=_int("CPU_THREADS", 2),
            embedding_batch_size=_int("EMBEDDING_BATCH_SIZE", 12),
            embedding_max_length=_int("EMBEDDING_MAX_LENGTH", 384),
            top_k_default=_int("RAG_TOP_K", 3),
            rag_candidate_pool=_int("RAG_CANDIDATE_POOL", 15),
            semantic_candidates=_int("RAG_SEMANTIC_CANDIDATES", 30),
            lexical_candidates=_int("RAG_LEXICAL_CANDIDATES", 30),
            max_context_chars=_int("MAX_CONTEXT_CHARS", 4000),
            max_chunk_chars_in_prompt=_int("MAX_EVIDENCE_CHARS", 800),
            semantic_weight=_float("RAG_SEMANTIC_WEIGHT", 0.65),
            lexical_weight=_float("RAG_LEXICAL_WEIGHT", 0.20),
            metadata_weight=_float("RAG_METADATA_WEIGHT", 0.15),
            review_threshold=_float("REVIEW_CONFIDENCE_THRESHOLD", 0.60),
            max_new_tokens=_int("GEMINI_MAX_OUTPUT_TOKENS", 800),
            gemini_timeout_seconds=_float("GEMINI_TIMEOUT_SECONDS", 30.0),
            gemini_max_retries=_int("GEMINI_MAX_RETRIES", 2),
            gemini_web_search=_bool("GEMINI_BUSQUEDA_WEB", True),
            interpretation_enabled=_bool("GEMINI_INTERPRETATION_ENABLED", True),
            final_selection_enabled=_bool("GEMINI_FINAL_SELECTION_ENABLED", True),
            skip_heavy_startup=_bool("SKIP_HEAVY_STARTUP", False),
        )

    def ensure_dirs(self) -> None:
        for path in (self.knowledge_dir, self.index_dir, self.cache_dir):
            path.mkdir(parents=True, exist_ok=True)
