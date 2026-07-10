"""Tests for SentimentProviderFactory — name -> provider dispatch (AC7)."""
from __future__ import annotations

import pytest

from src.analyzer.sentiment_providers.factory import SentimentProviderFactory
from src.analyzer.sentiment_providers.providers.vader import VaderSentimentProvider


def test_create_vader_returns_vader_provider():
    result = SentimentProviderFactory.create("vader")

    assert isinstance(result, VaderSentimentProvider)


def test_create_transformer_returns_transformer_provider():
    result = SentimentProviderFactory.create("transformer")

    assert type(result).__name__ == "TransformerSentimentProvider"


@pytest.mark.parametrize("bad_provider", ["", None, "bogus"])
def test_create_unknown_provider_raises_value_error(bad_provider):
    with pytest.raises(ValueError, match="vader"):
        SentimentProviderFactory.create(bad_provider)
