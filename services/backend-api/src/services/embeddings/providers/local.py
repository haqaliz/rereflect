"""
LocalEmbeddingProvider — in-process, CPU, air-gappable embedding provider.

Uses sentence-transformers to run embedding models locally (no network call
per embed(), no API key). Mirrors the M5.1 TransformerSentimentProvider
lazy-singleton pattern in
services/analysis-engine/src/analyzer/sentiment_providers/providers/transformer.py:

  - Model loads once per process on first embed() call (double-checked
    locking), never in __init__ — constructing a provider instance must be
    cheap and side-effect free.
  - The cache is keyed by model id so multiple models can coexist in one
    process (e.g. during model-id migration — see Aspect 1, model-keyed
    matching).
  - `sentence_transformers` is imported lazily, INSIDE the loader function,
    so importing this module never pulls in torch.
  - Honours HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE so a self-hosted,
    air-gapped deployment with pre-cached weights never attempts a network
    call.

NO factory/settings wiring here (Task 2 of this aspect) — this module only
defines the provider class.
"""

from __future__ import annotations

import os
import threading

from src.services.embeddings.base import EmbeddingProvider

_singleton_lock = threading.Lock()
_loaded_models: dict[str, object] = {}


def _is_offline() -> bool:
    """True if either HF_HUB_OFFLINE or TRANSFORMERS_OFFLINE is set truthy."""
    return os.getenv("HF_HUB_OFFLINE") in ("1", "true", "True") or os.getenv(
        "TRANSFORMERS_OFFLINE"
    ) in ("1", "true", "True")


def _get_model(model_id: str):
    """Lazily load + cache a SentenceTransformer model once per process per
    model id (double-checked locking). Imports sentence_transformers here,
    NOT at module level — this function is the only place in this module
    that touches the heavy dep (and, transitively, torch)."""
    model = _loaded_models.get(model_id)
    if model is None:
        with _singleton_lock:
            model = _loaded_models.get(model_id)
            if model is None:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    model_id,
                    device="cpu",
                    local_files_only=_is_offline(),
                )
                _loaded_models[model_id] = model
    return model


class LocalEmbeddingProvider(EmbeddingProvider):
    """
    In-process CPU embedding provider backed by sentence-transformers.

    Model loads once per process on first embed() call (module-level
    singleton, keyed by model id, shared across every provider instance —
    mirrors PRD #9 for the sentiment transformer provider). CPU-only,
    deterministic, and air-gappable when HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE
    is set and weights are pre-cached.
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

    def __init__(self, model: str | None = None) -> None:
        self._model = model or self.DEFAULT_MODEL
        self._dimension: int | None = None  # derived from first embed() call

    def embed(self, text: str) -> list[float]:
        """
        Encode text into an embedding vector using the configured model.

        Args:
            text: Input text to embed. May be empty.

        Returns:
            Flat list of floats; length equals the model's native dimension.
        """
        m = _get_model(self._model)
        vec = m.encode(text or "", normalize_embeddings=False)

        # Coerce numpy output to a flat Python list of floats. A single-input
        # encode() call may return a 2-D array (shape (1, n)) depending on
        # the model/pooling config — take row 0 in that case.
        if hasattr(vec, "tolist"):
            vec = vec.tolist()
        if vec and isinstance(vec[0], (list, tuple)):
            vec = vec[0]
        result = [float(v) for v in vec]

        self._dimension = len(result)
        return result

    @property
    def dimension(self) -> int:
        """
        Return the embedding dimension derived from the last embed() call.

        Returns 0 before the first call (unknown until the model has run).
        """
        return self._dimension if self._dimension is not None else 0
