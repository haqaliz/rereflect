from __future__ import annotations
from .base import SentimentProvider


class SentimentProviderFactory:
    """Name -> SentimentProvider. Lazy per-branch imports so requesting 'vader' never
    imports torch/transformers (mirrors EmbeddingProviderFactory.create)."""

    @staticmethod
    def create(provider: str) -> SentimentProvider:
        if not provider:
            raise ValueError(
                f"Unknown sentiment provider: {provider!r}. Supported: vader, transformer."
            )
        if provider == "vader":
            from .providers.vader import VaderSentimentProvider
            return VaderSentimentProvider()
        elif provider == "transformer":
            from .providers.transformer import TransformerSentimentProvider
            return TransformerSentimentProvider()
        else:
            raise ValueError(
                f"Unknown sentiment provider: {provider!r}. Supported: vader, transformer."
            )
