from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from app.services.clasificador.bm25 import LightweightBM25
from app.services.clasificador.config import Settings
from app.services.clasificador.documents import Chunk, DocumentLoader
from app.services.clasificador.hashing import sha256_file, stable_id
from app.services.clasificador.schemas import RAGEvidence
from app.services.clasificador.text import normalize_for_search
from app.services.clasificador.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchHit:
    chunk: Chunk
    score: float
    semantic_score: float
    lexical_score: float
    metadata_score: float


class HybridRAG:
    def __init__(self, settings: Settings, embedder):
        self.settings = settings
        self.embedder = embedder
        self.loader = DocumentLoader(settings.knowledge_dir)
        self.vector_store = VectorStore(settings.index_dir)
        self.chunks: list[Chunk] = []
        self.embeddings: np.ndarray = np.zeros((0, 1), dtype=np.float32)
        self.bm25 = LightweightBM25([])
        self.manifest: dict[str, Any] = {}
        self._lock = threading.RLock()
        self.source_weights = self._load_source_weights()
        self._ciiu_sections: dict[str, list[Chunk]] = {}
        self.load_existing()

    def _index_ciiu_sections(self) -> None:
        sections: dict[str, list[Chunk]] = {}
        heading = re.compile(r"Clase:\s*(\d{4})\s*[-–]", re.IGNORECASE)
        for chunk in self.chunks:
            if not chunk.source.replace("\\", "/").lower().startswith("ciiu/"):
                continue
            matches = list(heading.finditer(chunk.content))
            for i, match in enumerate(matches):
                section = chunk.content[match.start():matches[i + 1].start() if i + 1 < len(matches) else None]
                exact = Chunk(stable_id(chunk.id, match.group(1)), section, chunk.source,
                              {**chunk.metadata, "ciiu": match.group(1), "retrieval": "exact"}, chunk.source_weight)
                sections.setdefault(match.group(1), []).append(exact)
        self._ciiu_sections = sections

    def retrieve_ciiu_exact(self, code: str) -> list[SearchHit]:
        return [SearchHit(chunk, 1.0, 1.0, 1.0, 1.0) for chunk in self._ciiu_sections.get(str(code).strip(), [])]

    @property
    def backend(self) -> str:
        return self.vector_store.backend

    def _load_source_weights(self) -> dict[str, Any]:
        if not self.settings.source_weights_path.exists():
            return {"default_weight": 1.0, "sources": []}
        with self.settings.source_weights_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"default_weight": 1.0, "sources": []}

    def source_weight(self, relpath: str) -> float:
        normalized = relpath.replace("\\", "/").lower()
        for item in self.source_weights.get("sources", []):
            pattern = str(item.get("pattern", "")).lower()
            if pattern and pattern in normalized:
                return float(item.get("weight", 1.0))
        return float(self.source_weights.get("default_weight", 1.0))

    def load_existing(self) -> bool:
        manifest_path = self.settings.index_dir / "manifest.json"
        chunks_path = self.settings.index_dir / "chunks.jsonl"
        if not manifest_path.exists() or not chunks_path.exists() or not self.vector_store.load():
            return False
        try:
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.chunks = []
            with chunks_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        self.chunks.append(Chunk.from_dict(json.loads(line)))
            if any(self._excluded_source(c.source) for c in self.chunks):
                logger.warning("Índice contiene fuentes excluidas; se requiere reindexar")
                self.chunks = []
                return False
            self.embeddings = self.vector_store.matrix if self.vector_store.matrix is not None else np.zeros((0, 1), dtype=np.float32)
            if len(self.chunks) != len(self.embeddings):
                logger.warning("Índice inconsistente; se requiere reindexar")
                self.chunks = []
                self.embeddings = np.zeros((0, 1), dtype=np.float32)
                return False
            self.bm25 = LightweightBM25([c.content for c in self.chunks])
            self._index_ciiu_sections()
            return True
        except Exception as exc:
            logger.warning("No se pudo cargar índice existente: %s", exc)
            return False

    def _cache_paths(self, key: str) -> tuple[Path, Path]:
        return self.settings.cache_dir / f"{key}.npy", self.settings.cache_dir / f"{key}.jsonl"

    def _write_doc_cache(self, key: str, vectors: np.ndarray, chunks: list[Chunk]) -> None:
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
        vec_path, chunk_path = self._cache_paths(key)
        np.save(vec_path, vectors.astype(np.float32))
        with chunk_path.open("w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")

    def _read_doc_cache(self, key: str) -> tuple[np.ndarray, list[Chunk]]:
        vec_path, chunk_path = self._cache_paths(key)
        vectors = np.load(vec_path).astype(np.float32)
        chunks: list[Chunk] = []
        with chunk_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    chunks.append(Chunk.from_dict(json.loads(line)))
        return vectors, chunks

    def update(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            self.settings.ensure_dirs()
            old_manifest = self.manifest if self.manifest.get("embedding_model") == self.settings.embedding_model else {}
            old_docs = old_manifest.get("documents", {}) if not force else {}
            current_paths = self.loader.list_documents()
            current_rel = {p.resolve().relative_to(self.settings.knowledge_dir.resolve()).as_posix(): p for p in current_paths}

            new_docs: dict[str, Any] = {}
            updated = reused = removed = embeddings_recomputed = 0

            for relpath, path in sorted(current_rel.items()):
                file_hash = sha256_file(path)
                old = old_docs.get(relpath)
                if old and old.get("sha256") == file_hash:
                    key = old.get("cache_key")
                    vec_path, chunk_path = self._cache_paths(key)
                    if vec_path.exists() and chunk_path.exists():
                        new_docs[relpath] = old
                        reused += 1
                        continue

                weight = self.source_weight(relpath)
                chunks = self.loader.load(path, source_weight=weight)
                texts = [c.content for c in chunks]
                vectors = self.embedder.encode_passages(texts) if texts else np.zeros((0, getattr(self.embedder, "dimension", 384) or 384), dtype=np.float32)
                key = stable_id(self.settings.embedding_model, relpath, file_hash)
                self._write_doc_cache(key, vectors, chunks)
                new_docs[relpath] = {
                    "sha256": file_hash,
                    "cache_key": key,
                    "chunk_count": len(chunks),
                    "source_weight": weight,
                }
                updated += 1
                embeddings_recomputed += len(chunks)

            for relpath, old in old_docs.items():
                if relpath not in current_rel:
                    removed += 1
                    key = old.get("cache_key")
                    if key:
                        for p in self._cache_paths(key):
                            try:
                                p.unlink(missing_ok=True)
                            except Exception:
                                pass

            all_vectors: list[np.ndarray] = []
            all_chunks: list[Chunk] = []
            for relpath in sorted(new_docs):
                vectors, chunks = self._read_doc_cache(new_docs[relpath]["cache_key"])
                if len(vectors) != len(chunks):
                    raise RuntimeError(f"Cache inconsistente para {relpath}")
                if len(vectors):
                    all_vectors.append(vectors)
                    all_chunks.extend(chunks)

            if all_vectors:
                matrix = np.ascontiguousarray(np.vstack(all_vectors).astype(np.float32))
            else:
                dim = getattr(self.embedder, "dimension", 384) or 384
                matrix = np.zeros((0, dim), dtype=np.float32)

            self.vector_store.build(matrix)
            self.vector_store.save()
            self.embeddings = matrix
            self.chunks = all_chunks
            self.bm25 = LightweightBM25([c.content for c in self.chunks])
            self._index_ciiu_sections()
            self.manifest = {
                "version": 1,
                "embedding_model": self.settings.embedding_model,
                "vector_backend": self.vector_store.backend,
                "documents": new_docs,
                "chunks_total": len(self.chunks),
            }
            (self.settings.index_dir / "manifest.json").write_text(json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            with (self.settings.index_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
                for chunk in self.chunks:
                    f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")

            return {
                "backend": self.vector_store.backend,
                "documents_total": len(new_docs),
                "documents_updated": updated,
                "documents_reused": reused,
                "documents_removed": removed,
                "chunks_total": len(self.chunks),
                "embeddings_recomputed": embeddings_recomputed,
            }

    def _metadata_score(self, content: str, facts: dict[str, Any]) -> float:
        text = normalize_for_search(content)
        score = 0.0
        weights = {
            "provider_ruc": 0.35,
            "company_ruc": 0.10,
            "counterparty_ciiu": 0.20,
            "company_ciiu": 0.15,
            "tipo_cp": 0.10,
            "libro": 0.10,
        }
        for key, weight in weights.items():
            value = facts.get(key)
            if value is None:
                continue
            values = value if isinstance(value, (list, tuple, set)) else [value]
            if any(normalize_for_search(str(v)) in text for v in values if str(v).strip()):
                score += weight
        return min(1.0, score)

    @staticmethod
    def _excluded_source(source: str) -> bool:
        return bool(set(source.replace("\\", "/").lower().split("/")) & {"historico", "histórico", "historical", "history"})

    def account_siblings(self, codes: list[str], facts: dict[str, Any]) -> list[SearchHit]:
        """Expande hojas hermanas de una familia ya recuperada del plan vigente."""
        prefixes = {code[:4] for code in codes if len(code) >= 4 and code.isdigit()}
        if not prefixes:
            return []
        result: list[SearchHit] = []
        for chunk in self.chunks:
            if not chunk.source.replace("\\", "/").lower().startswith("plan_cuentas/"):
                continue
            code = str(chunk.metadata.get("cuenta") or chunk.metadata.get("codigo") or "")
            if not code:
                match = re.search(r"(?:col_[34]|cuenta)\s*[:#]?\s*(\d+)", chunk.content, re.IGNORECASE)
                code = match.group(1) if match else ""
            if code and len(code) > 4 and code[:4] in prefixes:
                result.append(SearchHit(chunk, 0.5, 0.5, 0.5, self._metadata_score(chunk.content, facts)))
        return result

    def account_descendants(self, query: str, direction: str, nature: str, area: str, stage: str) -> list[SearchHit]:
        """Recupera hojas del plan por jerarquía estructural después de interpretar la operación."""
        if stage == "total_account":
            prefix = "121" if direction.upper() == "VENTA" else "421"
        elif direction.upper() == "VENTA" and "SERVICIO" in nature.upper():
            prefix = "703"
        elif direction.upper() == "COMPRA" and area == "MERCADERIA":
            prefix = "601"
        else:
            return []
        result: list[SearchHit] = []
        for chunk in self.chunks:
            source = chunk.source.replace("\\", "/").lower()
            if not source.startswith("plan_cuentas/"):
                continue
            code = str(chunk.metadata.get("cuenta") or chunk.metadata.get("codigo") or "")
            if not code:
                import re
                match = re.search(r"(?:col_[34]|cuenta)\s*[:#]?\s*(\d+)", chunk.content, re.IGNORECASE)
                code = match.group(1) if match else ""
            if code.startswith(prefix):
                specificity = min(1.0, len(code) / 7)
                result.append(SearchHit(chunk, 0.75 + 0.15 * specificity, 0.8, 0.8, 0.5))
        return sorted(result, key=lambda h: (len(str(h.chunk.metadata.get("cuenta") or "")), h.score), reverse=True)

    @staticmethod
    def _routing_multiplier(source: str, facts: dict[str, Any]) -> float:
        """Enruta por el libro explícito sin clasificar el contenido.

        Si el comprobante ya viene de VENTAS, el subconjunto RAG de compras es ruido,
        y viceversa. El plan completo, PCGE, CIIU y tributario permanecen disponibles.
        """
        src = source.replace("\\", "/").lower()
        libro = normalize_for_search(str(facts.get("libro") or ""))
        if libro == "ventas":
            if "cuentas_reporte_ventas_rag.xlsx" in src:
                return 1.08
            if "cuentas_reporte_compras_rag.xlsx" in src:
                return 0.10
        elif libro == "compras":
            if "cuentas_reporte_compras_rag.xlsx" in src:
                return 1.08
            if "cuentas_reporte_ventas_rag.xlsx" in src:
                return 0.10
        return 1.0

    @staticmethod
    def _purpose_allowed(source: str, purpose: str | None, content: str = "") -> bool:
        if HybridRAG._excluded_source(source):
            return False
        if not purpose:
            return True
        normalized = source.replace("\\", "/").lower()
        account_source = (
            "plan_cuentas/" in normalized
            or normalized.startswith("pcge/")
        )
        if purpose == "context":
            return normalized.startswith("ciiu/")
        if purpose == "tax":
            return normalized.startswith("tributario/")
        if purpose in {"base_account", "base_account_leaf", "total_account"}:
            if purpose == "total_account" and "plan_cuentas/" in normalized:
                total_terms = normalize_for_search(content)
                return any(term in total_terms for term in ("por pagar", "cuentas por pagar", "emitidas", "por cobrar", "cuentas por cobrar"))
            return account_source
        return True

    def search_tax(self, query: str) -> list[SearchHit]:
        hits, _ = self.search(query, top_k=3, purpose="tax")
        return [hit for hit in hits if hit.score >= 0.45]

    def search(
        self,
        query: str,
        top_k: int | None = None,
        facts: dict[str, Any] | None = None,
        purpose: str | None = None,
    ) -> tuple[list[SearchHit], float]:
        with self._lock:
            if not self.chunks or self.embeddings.size == 0:
                return [], 0.0
            facts = facts or {}
            top_k = max(1, min(top_k or self.settings.top_k_default, max(10, self.settings.rag_candidate_pool)))
            qv = self.embedder.encode_queries([query])[0]
            _, sem_idx = self.vector_store.search(qv, max(top_k, self.settings.semantic_candidates))
            bm25_scores = self.bm25.scores(query)
            lex_n = min(len(bm25_scores), max(top_k, self.settings.lexical_candidates))
            lex_idx = np.argsort(bm25_scores)[::-1][:lex_n] if lex_n else np.array([], dtype=np.int64)
            candidates = sorted(
                i for i in (set(int(i) for i in sem_idx if i >= 0) | set(int(i) for i in lex_idx if i >= 0))
                if self._purpose_allowed(self.chunks[i].source, purpose, self.chunks[i].content)
                and (purpose != "total_account" or self._total_direction_allowed(self.chunks[i], query))
            )
            if not candidates:
                return [], 0.0
            max_bm25 = float(bm25_scores[candidates].max()) if candidates else 0.0
            hits: list[SearchHit] = []
            for i in candidates:
                semantic_raw = float(np.dot(qv, self.embeddings[i]))
                semantic = max(0.0, min(1.0, (semantic_raw + 1.0) / 2.0))
                lexical = float(bm25_scores[i] / max_bm25) if max_bm25 > 0 else 0.0
                metadata = self._metadata_score(self.chunks[i].content, facts)
                base = (
                    self.settings.semantic_weight * semantic
                    + self.settings.lexical_weight * lexical
                    + self.settings.metadata_weight * metadata
                )
                routed = self._routing_multiplier(self.chunks[i].source, facts)
                weighted = max(0.0, min(1.0, base * float(self.chunks[i].source_weight) * routed))
                hits.append(SearchHit(self.chunks[i], weighted, semantic, lexical, metadata))
            hits.sort(key=lambda h: h.score, reverse=True)
            hits = self._diversify(hits, top_k)
            confidence = self._confidence(hits)
            return hits, confidence

    @staticmethod
    def _total_direction_allowed(chunk: Chunk, query: str) -> bool:
        import re
        code = str(chunk.metadata.get("cuenta") or chunk.metadata.get("codigo") or "")
        if not code:
            match = re.search(r"(?:col_[34]|cuenta)\s*[:#]?\s*(\d+)", chunk.content, re.IGNORECASE)
            code = match.group(1) if match else ""
        direction = query.splitlines()[0].strip().upper()
        if direction == "VENTA":
            return code.startswith("12") or (not code and "por cobrar" in normalize_for_search(chunk.content))
        if direction == "COMPRA":
            return code.startswith("42") or (not code and "por pagar" in normalize_for_search(chunk.content))
        return False

    @staticmethod
    def _source_group(source: str) -> str:
        normalized = source.replace("\\", "/")
        # En plan_cuentas cada archivo cumple un rol distinto (plan completo vs.
        # subconjuntos RAG compras/ventas), por eso se diversifican por archivo.
        if normalized.startswith("plan_cuentas/"):
            return normalized
        return normalized.split("/", 1)[0] if "/" in normalized else normalized

    @classmethod
    def _diversify(cls, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        """Evita que el Top-K quede ocupado por filas casi idénticas de una sola fuente.

        Reserva hasta tres posiciones para grupos de conocimiento distintos (plan, CIIU,
        tributario, PCGE, etc.) y completa el resto por score global. No introduce reglas
        contables; solo diversidad de evidencia.
        """
        if len(hits) <= top_k:
            return hits
        best = hits[0].score if hits else 0.0
        threshold = best * 0.55
        selected: list[SearchHit] = []
        used_ids: set[str] = set()
        groups: set[str] = set()
        diversity_slots = min(3, top_k)
        for hit in hits:
            if len(selected) >= diversity_slots:
                break
            group = cls._source_group(hit.chunk.source)
            if group in groups or hit.score < threshold:
                continue
            selected.append(hit)
            used_ids.add(hit.chunk.id)
            groups.add(group)
        for hit in hits:
            if len(selected) >= top_k:
                break
            if hit.chunk.id in used_ids:
                continue
            selected.append(hit)
            used_ids.add(hit.chunk.id)
        return selected

    @staticmethod
    def _confidence(hits: list[SearchHit]) -> float:
        if not hits:
            return 0.0
        rank_weights = [0.58, 0.25, 0.10, 0.05, 0.02]
        used = rank_weights[:len(hits)]
        weighted = sum(h.score * w for h, w in zip(hits, used, strict=False)) / sum(used)
        coverage = min(1.0, len(hits) / 3.0)
        return round(max(0.0, min(0.99, weighted * (0.85 + 0.15 * coverage))), 4)


    def search_multi(
        self,
        queries: list[str],
        top_k: int | None = None,
        facts: dict[str, Any] | None = None,
        purpose: str | None = None,
    ) -> tuple[list[SearchHit], float]:
        """Combina unas pocas consultas complementarias sin aumentar el Top-K final.

        Se usa para separar contexto de actividad y búsqueda contable, evitando que una
        sola formulación domine la recuperación. Los scores se fusionan por máximo.
        """
        top_k = max(1, min(top_k or self.settings.top_k_default, max(10, self.settings.rag_candidate_pool)))
        merged: dict[str, SearchHit] = {}
        per_query_k = min(max(10, self.settings.rag_candidate_pool), max(6, top_k * 2))
        for query in queries:
            if not query.strip():
                continue
            hits, _ = self.search(query, top_k=per_query_k, facts=facts, purpose=purpose)
            for hit in hits:
                prev = merged.get(hit.chunk.id)
                if prev is None or hit.score > prev.score:
                    merged[hit.chunk.id] = hit
        ranked = sorted(merged.values(), key=lambda h: h.score, reverse=True)
        final_hits = self._diversify(ranked, top_k)
        return final_hits, self._confidence(final_hits)

    def evidence(self, hits: list[SearchHit]) -> list[RAGEvidence]:
        result: list[RAGEvidence] = []
        for h in hits:
            result.append(RAGEvidence(
                source=h.chunk.source,
                score=round(h.score, 4),
                semantic_score=round(h.semantic_score, 4),
                lexical_score=round(h.lexical_score, 4),
                metadata_score=round(h.metadata_score, 4),
                source_weight=round(h.chunk.source_weight, 3),
                snippet=h.chunk.content[:700],
                metadata=h.chunk.metadata,
            ))
        return result
