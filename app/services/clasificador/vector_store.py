from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover - fallback is intentionally supported
    faiss = None


class VectorStore:
    def __init__(self, index_dir: Path):
        self.index_dir = index_dir
        self.backend = "faiss" if faiss is not None else "numpy-fallback"
        self.index = None
        self.matrix: np.ndarray | None = None

    def build(self, vectors: np.ndarray) -> None:
        vectors = np.ascontiguousarray(vectors.astype(np.float32))
        self.matrix = vectors
        if faiss is not None:
            dim = int(vectors.shape[1]) if vectors.ndim == 2 and vectors.size else 0
            if dim == 0:
                self.index = None
                return
            index = faiss.IndexFlatIP(dim)
            index.add(vectors)
            self.index = index
        else:
            self.index = None

    def save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        if self.matrix is not None:
            np.save(self.index_dir / "embeddings.npy", self.matrix)
        if faiss is not None and self.index is not None:
            faiss.write_index(self.index, str(self.index_dir / "index.faiss"))

    def load(self) -> bool:
        matrix_path = self.index_dir / "embeddings.npy"
        if not matrix_path.exists():
            return False
        self.matrix = np.load(matrix_path).astype(np.float32)
        faiss_path = self.index_dir / "index.faiss"
        if faiss is not None and faiss_path.exists():
            self.index = faiss.read_index(str(faiss_path))
            self.backend = "faiss"
        else:
            self.index = None
            self.backend = "numpy-fallback"
        return True

    def search(self, query_vector: np.ndarray, top_n: int) -> tuple[np.ndarray, np.ndarray]:
        if self.matrix is None or len(self.matrix) == 0:
            return np.array([], dtype=np.float32), np.array([], dtype=np.int64)
        q = np.ascontiguousarray(query_vector.reshape(1, -1).astype(np.float32))
        top_n = max(1, min(top_n, len(self.matrix)))
        if faiss is not None and self.index is not None:
            scores, idx = self.index.search(q, top_n)
            return scores[0], idx[0]
        scores = self.matrix @ q[0]
        idx = np.argsort(scores)[::-1][:top_n]
        return scores[idx], idx.astype(np.int64)
