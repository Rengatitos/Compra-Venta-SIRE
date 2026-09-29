"""Índice incremental y recuperación híbrida del clasificador (portado de su API original)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from app.services.clasificador.config import Settings
from app.services.clasificador.rag import HybridRAG
from app.services.clasificador.text import tokenize


class HashEmbedder:
    loaded = True
    dimension = 64

    def _encode(self, texts):
        rows = []
        for text in texts:
            v = np.zeros(self.dimension, dtype=np.float32)
            for tok in tokenize(text):
                idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dimension
                v[idx] += 1.0
            n = np.linalg.norm(v)
            if n:
                v /= n
            rows.append(v)
        return np.vstack(rows) if rows else np.zeros((0, self.dimension), dtype=np.float32)

    def encode_passages(self, texts):
        return self._encode(texts)

    def encode_queries(self, texts):
        return self._encode(texts)


def test_incremental_index_and_retrieval(tmp_path: Path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "rules.md").write_text("Cuenta 6011020 MERCADERIAS Compras de bebidas para reventa.\nCuenta 70321 Servicios terminados venta local hospedaje.", encoding="utf-8")
    settings = Settings.from_env(tmp_path)
    settings.knowledge_dir = knowledge
    settings.index_dir = tmp_path / "index"
    settings.cache_dir = tmp_path / "cache"
    settings.source_weights_path = tmp_path / "none.yaml"
    rag = HybridRAG(settings, HashEmbedder())
    first = rag.update(False)
    assert first["embeddings_recomputed"] > 0
    second = rag.update(False)
    assert second["embeddings_recomputed"] == 0
    hits, conf = rag.search("compra bebidas mercaderias", top_k=3, facts={"libro":"compras"})
    assert hits
    assert "6011020" in hits[0].chunk.content
    assert 0 <= conf <= 1


def test_el_gemini_pro_esta_apagado_y_se_usa_el_modelo_barato(monkeypatch):
    from app.services.clasificador import config

    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.delenv("GEMINI_PRO_HABILITADO", raising=False)
    assert config.GEMINI_PRO_HABILITADO is False
    assert config.modelo_gemini() == config.MODELO_BARATO == "gemini-3.5-flash-lite"

    monkeypatch.setenv("GEMINI_PRO_HABILITADO", "true")
    assert config.modelo_gemini() == "gemini-3.1-pro-preview"

    monkeypatch.delenv("GEMINI_MODEL")
    assert config.modelo_gemini() == "gemini-3.5-flash-lite"
