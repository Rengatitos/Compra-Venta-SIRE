from __future__ import annotations

import logging

import numpy as np

from app.services.clasificador.config import Settings

logger = logging.getLogger(__name__)


class MultilingualE5Embedder:
    """Embeddings multilingües usando Transformers directamente, sin SentenceTransformers."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None
        self.tokenizer = None
        self.torch = None
        self._loaded = False
        self.dimension: int | None = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        if self._loaded:
            return
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("Faltan torch/transformers. Instale requirements.txt") from exc
        self.torch = torch
        torch.set_num_threads(max(1, self.settings.cpu_threads))
        kwargs = {"cache_dir": self.settings.hf_home, "token": self.settings.hf_token}
        self.tokenizer = AutoTokenizer.from_pretrained(self.settings.embedding_model, **kwargs)
        self.model = AutoModel.from_pretrained(self.settings.embedding_model, low_cpu_mem_usage=True, **kwargs)
        self.model.eval()
        if self.settings.embedding_dynamic_int8 and not torch.cuda.is_available():
            try:
                self.model = torch.ao.quantization.quantize_dynamic(self.model, {torch.nn.Linear}, dtype=torch.qint8)
                logger.info("Embedding model cuantizado dinámicamente a int8 en CPU")
            except Exception as exc:
                logger.warning("No se pudo aplicar int8 al embedding model: %s", exc)
        self.dimension = int(getattr(self.model.config, "hidden_size", 384))
        self._loaded = True

    def _mean_pool(self, model_output, attention_mask):
        torch = self.torch
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def _encode(self, texts: list[str], prefix: str) -> np.ndarray:
        if not self._loaded:
            self.load()
        assert self.tokenizer is not None and self.model is not None and self.torch is not None
        torch = self.torch
        all_vectors: list[np.ndarray] = []
        batch_size = max(1, self.settings.embedding_batch_size)
        with torch.inference_mode():
            for start in range(0, len(texts), batch_size):
                batch = [prefix + t for t in texts[start:start + batch_size]]
                encoded = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self.settings.embedding_max_length,
                    return_tensors="pt",
                )
                output = self.model(**encoded)
                pooled = self._mean_pool(output, encoded["attention_mask"])
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                all_vectors.append(pooled.detach().cpu().to(torch.float32).numpy())
        if not all_vectors:
            dim = self.dimension or 384
            return np.zeros((0, dim), dtype=np.float32)
        return np.ascontiguousarray(np.vstack(all_vectors).astype(np.float32))

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "passage: ")

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "query: ")
