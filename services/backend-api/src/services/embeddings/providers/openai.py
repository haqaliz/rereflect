"""
OpenAI embedding provider.

Mirrors the embedding call already in template_matcher._call_embedding_api
(L120-134), but wraps it in the EmbeddingProvider interface so it is
injectable and testable without patching inside template_matcher.

Default model: text-embedding-3-small (1536-dim)
Dimension: derived from the actual response length, never hardcoded.
"""

from __future__ import annotations

import openai

from src.services.embeddings.base import EmbeddingProvider

_DEFAULT_MODEL = "text-embedding-3-small"


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider backed by the OpenAI Embeddings API.

    Requires a valid BYOK API key — the org's key retrieved via
    resolve_org_byok_key.  There is no system-key fallback (PRD §A4).
    """

    DEFAULT_MODEL: str = _DEFAULT_MODEL

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        """
        Args:
            api_key: OpenAI API key. Must be non-empty; empty/None raises
                     ValueError at embed() time.
            model:   Model ID. Defaults to text-embedding-3-small.
        """
        self._api_key = api_key
        self._model = model
        self._dimension: int | None = None  # derived from first response

    def embed(self, text: str) -> list[float]:
        """
        Call the OpenAI Embeddings API and return a flat list of floats.

        Raises:
            ValueError / RuntimeError: If api_key is empty/None.
            openai.APIError: On network or authentication failure.
        """
        if not self._api_key:
            raise ValueError(
                "No OpenAI API key configured for embeddings. "
                "Please add your OpenAI key in Settings → AI → API Keys."
            )

        client = openai.OpenAI(api_key=self._api_key)
        response = client.embeddings.create(
            model=self._model,
            input=text,
        )
        vector: list[float] = response.data[0].embedding
        self._dimension = len(vector)
        return vector

    @property
    def dimension(self) -> int:
        """
        Return the dimension derived from the last embed() call.

        If embed() has not been called yet, returns the known dimension for
        standard models, or 0 as a sentinel that triggers a lazy embed call
        in consumers.
        """
        if self._dimension is not None:
            return self._dimension
        # Provide the well-known dimension for default model so that
        # dimension can be read before the first embed() call.
        _KNOWN = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return _KNOWN.get(self._model, 0)
