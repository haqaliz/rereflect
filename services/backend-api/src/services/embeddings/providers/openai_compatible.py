"""
OpenAI-compatible embedding provider (keyless / local).

Targets any server that exposes the OpenAI Embeddings API format:
  - Ollama (http://localhost:11434/v1)
  - LM Studio, vLLM, llama.cpp, or any OpenAI-compatible endpoint

Key differences from the cloud OpenAI provider:
  - No API key required; the SDK requires a non-empty string, so we use the
    dummy key "ollama" when none is supplied (mirrors the worker factory).
  - base_url is REQUIRED — there is no sensible global default.
  - dimension is always derived from the actual response (local models vary).
"""

from __future__ import annotations

import openai

from src.services.embeddings.base import EmbeddingProvider

_DUMMY_KEY = "ollama"  # placeholder required by the openai SDK, not validated by local endpoints


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider for any OpenAI-API-compatible local/remote endpoint.

    Compatible with Ollama, vLLM, LM Studio, llama.cpp server, and similar.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
    ) -> None:
        """
        Args:
            base_url: Required. Full base URL of the compatible server,
                      e.g. "http://localhost:11434/v1".
            model:    Required. Model ID to use, e.g. "nomic-embed-text".
            api_key:  Optional. If None/empty, the dummy key "ollama" is used
                      (the openai SDK requires a non-empty api_key, but local
                      servers don't validate it).
        """
        if not base_url:
            raise ValueError(
                "base_url is required for OpenAICompatibleEmbeddingProvider. "
                "Set OrgAIConfig.base_url to the endpoint URL "
                "(e.g. 'http://localhost:11434/v1')."
            )
        self._base_url = base_url
        self._model = model
        self._api_key = api_key or _DUMMY_KEY
        self._dimension: int | None = None  # derived from first response

    def embed(self, text: str) -> list[float]:
        """
        Call the local OpenAI-compatible embeddings endpoint.

        Args:
            text: Input text to embed.

        Returns:
            Flat list of floats; length equals the model's native dimension.

        Raises:
            openai.APIConnectionError: When the local endpoint is unreachable.
        """
        client = openai.OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
        )
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
        Return the embedding dimension derived from the last embed() call.

        Returns 0 before the first call (unknown — depends on the local model).
        """
        return self._dimension if self._dimension is not None else 0
