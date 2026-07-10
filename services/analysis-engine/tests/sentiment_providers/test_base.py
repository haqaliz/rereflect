"""Tests for the SentimentProvider ABC + SentimentScore contract (AC3)."""
from __future__ import annotations

import pytest

from src.analyzer.sentiment_providers.base import SentimentProvider, SentimentScore


def test_sentiment_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        SentimentProvider()  # type: ignore[abstract]


def test_subclass_without_score_cannot_be_instantiated():
    class IncompleteProvider(SentimentProvider):
        pass

    with pytest.raises(TypeError):
        IncompleteProvider()  # type: ignore[abstract]


def test_minimal_concrete_subclass_can_be_instantiated_and_scores():
    class MinimalProvider(SentimentProvider):
        def score(self, text: str) -> SentimentScore:
            return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0}

    provider = MinimalProvider()
    result = provider.score("x")

    assert isinstance(result, dict)
    assert set(result.keys()) == {"compound", "pos", "neu", "neg"}
