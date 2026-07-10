from __future__ import annotations
from .base import SentimentProvider


class SentimentProviderFactory:
    """Name -> SentimentProvider. Lazy per-branch imports so requesting 'vader' never
    imports torch/transformers (mirrors EmbeddingProviderFactory.create).

    NOTE: this is a Phase 3 stub handling only 'vader'; extended with the 'transformer'
    branch in Phase 4."""

    @staticmethod
    def create(provider: str) -> SentimentProvider:
        if not provider:
            raise ValueError(
                f"Unknown sentiment provider: {provider!r}. Supported: vader."
            )
        if provider == "vader":
            from .providers.vader import VaderSentimentProvider
            return VaderSentimentProvider()
        else:
            raise ValueError(
                f"Unknown sentiment provider: {provider!r}. Supported: vader."
            )
