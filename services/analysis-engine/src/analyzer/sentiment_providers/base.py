from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypedDict


class SentimentScore(TypedDict):
    """Raw provider output — 4 keys only. label/is_extreme/churn_risk are computed by
    SentimentAnalyzer from provider-independent logic, never by the provider."""
    compound: float
    pos: float
    neu: float
    neg: float


class SentimentProvider(ABC):
    """Pure sentiment scorer. No DB, no per-org config — see resolve_sentiment_provider
    (backend-api, per-org-resolution aspect) for org-scoped selection."""

    @abstractmethod
    def score(self, text: str) -> SentimentScore:
        """Return compound/pos/neu/neg for text. May raise on provider failure (model load,
        inference error) — the caller (SentimentAnalyzer.analyze) owns the VADER fallback,
        not this method and not the factory."""
        ...
