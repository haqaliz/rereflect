"""
EmbeddingProvider — abstract base class for all embedding providers.

Every provider must:
  - Implement embed(text: str) -> list[float]
      Normalise the provider SDK's response to a flat Python list of floats.
  - Expose a dimension property -> int
      Returns the length of the embedding vector for the active model.
      dimension must derive from the actual model output, never be hardcoded,
      so that dimension-aware storage (pgvector) is always correct.

Default model constants (for documentation / factory defaults):
  openai              : text-embedding-3-small (1536-dim)
  openai_compatible   : provider-dependent (e.g. nomic-embed-text → 768-dim)
  google              : text-embedding-004 (768-dim)
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """
    Abstract base class for all embedding providers.

    Subclasses must implement:
      - embed(text: str) -> list[float]
      - dimension property -> int
    """

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.

        Args:
            text: The input text to embed. May be empty; providers should
                  handle gracefully (return a zero-cost response or empty list).

        Returns:
            A flat list of floats representing the embedding vector.

        Raises:
            Exception: Provider-specific errors (network, auth) propagate to
                       the caller. The resolver does NOT call embed(); consumers
                       (template-matching-local, copilot-llm-local) own try/except.
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """
        Return the embedding dimension for the configured model.

        Must reflect the actual model output length, not a hardcoded constant.
        Load-bearing: used to create pgvector columns of the correct size in the
        template-matching-local aspect.

        Returns:
            Integer dimension, e.g. 1536 for text-embedding-3-small.
        """
        ...
