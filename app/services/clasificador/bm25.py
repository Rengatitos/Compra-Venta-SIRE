from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence

import numpy as np

from app.services.clasificador.text import tokenize


class LightweightBM25:
    def __init__(self, documents: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = [tokenize(d) for d in documents]
        self.n = len(self.docs)
        self.doc_len = np.array([len(d) for d in self.docs], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if self.n else 0.0
        self.tf = [Counter(d) for d in self.docs]
        df: dict[str, int] = defaultdict(int)
        for doc in self.docs:
            for term in set(doc):
                df[term] += 1
        self.idf = {
            term: math.log(1.0 + (self.n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def scores(self, query: str) -> np.ndarray:
        if self.n == 0:
            return np.zeros(0, dtype=np.float32)
        terms = tokenize(query)
        scores = np.zeros(self.n, dtype=np.float32)
        for term in terms:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf_doc in enumerate(self.tf):
                f = tf_doc.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * (self.doc_len[i] / (self.avgdl or 1.0)))
                scores[i] += idf * (f * (self.k1 + 1)) / denom
        return scores
