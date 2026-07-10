"""Tests for SentimentAnalyzer's runtime fallback to VADER when the configured provider's
score() raises (PRD #9) — analyze() must never raise."""
from __future__ import annotations

import logging

import pytest

from src.analyzer.sentiment import SentimentAnalyzer
from src.analyzer.sentiment_providers.base import SentimentProvider, SentimentScore
from src.analyzer.sentiment_providers.providers.vader import VaderSentimentProvider


class RaisingProvider(SentimentProvider):
    """Stub provider whose score() always raises — proves the analyzer-side fallback."""

    def __init__(self):
        self.call_count = 0

    def score(self, text: str) -> SentimentScore:
        self.call_count += 1
        raise RuntimeError("boom")


class SpyVaderProvider(VaderSentimentProvider):
    """VADER subclass that counts calls — used to prove the happy path never falls back."""

    def __init__(self):
        super().__init__()
        self.call_count = 0

    def score(self, text: str) -> SentimentScore:
        self.call_count += 1
        return super().score(text)


def test_analyze_does_not_raise_when_provider_score_fails():
    stub = RaisingProvider()
    analyzer = SentimentAnalyzer(provider=stub)

    result = analyzer.analyze("some text")  # must not raise

    assert set(result.keys()) == {
        'compound', 'pos', 'neu', 'neg', 'label', 'is_extreme', 'churn_risk'
    }


def test_analyze_falls_back_to_vader_values_on_provider_failure():
    text = "I'm going to cancel my subscription if this isn't fixed."
    stub = RaisingProvider()
    analyzer = SentimentAnalyzer(provider=stub)

    result = analyzer.analyze(text)

    direct_vader = VaderSentimentProvider().score(text)

    assert result['compound'] == pytest.approx(direct_vader['compound'])
    assert result['pos'] == pytest.approx(direct_vader['pos'])
    assert result['neu'] == pytest.approx(direct_vader['neu'])
    assert result['neg'] == pytest.approx(direct_vader['neg'])
    # label/is_extreme/churn_risk still computed correctly for the text
    assert result['churn_risk'] is True
    assert result['is_extreme'] is True


def test_analyze_logs_warning_on_provider_failure(caplog):
    stub = RaisingProvider()
    analyzer = SentimentAnalyzer(provider=stub)

    with caplog.at_level(logging.WARNING):
        analyzer.analyze("some text")

    assert any(
        'failed' in record.message.lower() or 'fall' in record.message.lower()
        for record in caplog.records
    )


def test_analyze_happy_path_never_invokes_fallback():
    spy = SpyVaderProvider()
    analyzer = SentimentAnalyzer(provider=spy)

    analyzer.analyze("Love the new interface! Great features and excellent design.")

    # The spy IS the primary provider here; ensure the fallback provider (separate VADER
    # instance) was never constructed/used since spy is a VaderSentimentProvider subclass —
    # analyzer should reuse spy itself as the fallback, not double-construct.
    assert spy.call_count == 1
    assert analyzer._fallback_provider is spy


def test_analyze_never_raises_when_both_primary_and_fallback_fail(caplog):
    """PRD #9: analyze() must TRULY never raise, even if the fallback provider itself raises."""
    text = "I'm going to cancel my subscription if this isn't fixed."
    primary = RaisingProvider()
    analyzer = SentimentAnalyzer(provider=primary)
    fallback = RaisingProvider()
    analyzer._fallback_provider = fallback

    with caplog.at_level(logging.ERROR):
        result = analyzer.analyze(text)  # must not raise

    assert list(result.keys()) == [
        'compound', 'pos', 'neu', 'neg', 'label', 'is_extreme', 'churn_risk'
    ]

    # Last-resort neutral score
    assert result['compound'] == 0.0
    assert result['pos'] == 0.0
    assert result['neu'] == 1.0
    assert result['neg'] == 0.0
    assert result['label'] == 'neutral'

    # is_extreme/churn_risk still computed from the text itself
    assert result['churn_risk'] is True
    assert result['is_extreme'] is True

    assert any(record.levelno == logging.ERROR for record in caplog.records)
