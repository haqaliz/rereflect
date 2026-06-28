"""
Google (Gemini) embedding provider.

Uses google-generativeai SDK (google-generativeai>=0.8.0, already in
requirements.txt for both backend-api and worker-service).

Note: the google.generativeai package has been marked as deprecated by Google
in favour of google.genai. We continue using it because:
  1. It is already a direct dependency of requirements.txt.
  2. The worker's Google LLM provider uses it too (consistency).
  3. Migrating to google.genai is a separate concern tracked in DEV-TRACKING.

SDK import is NOT lazy here because the dependency is already required by
requirements.txt — a missing SDK would be a packaging error, not a runtime
configuration issue.  The test suite mocks genai at the module level, so the
tests pass regardless of whether the SDK is installed.

Default model: models/text-embedding-004 (768-dim)
Dimension: derived from actual response, never hardcoded.
"""

from __future__ import annotations

import google.generativeai as genai

from src.services.embeddings.base import EmbeddingProvider

_DEFAULT_MODEL = "models/text-embedding-004"


class GoogleEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider backed by the Google Generative AI (Gemini) API.

    Uses genai.embed_content() and normalises the response dict to
    a flat list[float].
    """

    DEFAULT_MODEL: str = _DEFAULT_MODEL

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        """
        Args:
            api_key: Google AI API key. Must be non-empty.
            model:   Embedding model ID. Defaults to models/text-embedding-004.

        Raises:
            ValueError: If api_key is empty or None.
        """
        if not api_key:
            raise ValueError(
                "api_key is required for GoogleEmbeddingProvider. "
                "Please add your Google AI key in Settings → AI → API Keys."
            )
        self._api_key = api_key
        self._model = model
        self._dimension: int | None = None  # derived from first response

    def embed(self, text: str) -> list[float]:
        """
        Call the Google Generative AI embeddings API.

        Normalises the SDK's response dict {'embedding': [...]} to a flat
        list[float].

        Args:
            text: Input text to embed.

        Returns:
            Flat list of Python floats. Length equals the model's native
            dimension (768 for text-embedding-004).

        Raises:
            Exception: SDK errors (auth, quota, network) propagate to caller.
        """
        genai.configure(api_key=self._api_key)
        result = genai.embed_content(
            model=self._model,
            content=text,
        )
        # Normalise: result may be dict {'embedding': list} or an object
        raw = result["embedding"] if isinstance(result, dict) else result.embedding
        vector: list[float] = [float(v) for v in raw]
        self._dimension = len(vector)
        return vector

    @property
    def dimension(self) -> int:
        """
        Return the embedding dimension derived from the last embed() call.

        Returns 0 before the first embed() call.
        """
        return self._dimension if self._dimension is not None else 0
