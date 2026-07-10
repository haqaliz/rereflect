"""Tests for VaderSentimentProvider — proves the extraction adds zero transformation vs. calling
vaderSentiment directly (AC3)."""
from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.analyzer.sentiment_providers.providers.vader import VaderSentimentProvider


def test_score_returns_exactly_four_keys():
    provider = VaderSentimentProvider()
    result = provider.score("This is fine, nothing bad here.")

    assert set(result.keys()) == {"compound", "pos", "neu", "neg"}


def test_score_matches_vader_directly_for_fixed_input():
    text = "Love the new interface! Great features and excellent design."

    provider = VaderSentimentProvider()
    result = provider.score(text)

    direct = SentimentIntensityAnalyzer().polarity_scores(text)

    assert result["compound"] == direct["compound"]
    assert result["pos"] == direct["pos"]
    assert result["neu"] == direct["neu"]
    assert result["neg"] == direct["neg"]


def test_score_matches_vader_directly_for_negative_input():
    text = "Terrible app. Crashes constantly and horrible performance."

    provider = VaderSentimentProvider()
    result = provider.score(text)

    direct = SentimentIntensityAnalyzer().polarity_scores(text)

    assert result["compound"] == direct["compound"]
    assert result["pos"] == direct["pos"]
    assert result["neu"] == direct["neu"]
    assert result["neg"] == direct["neg"]
