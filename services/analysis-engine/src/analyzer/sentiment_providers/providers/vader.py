from __future__ import annotations
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from ..base import SentimentProvider, SentimentScore


class VaderSentimentProvider(SentimentProvider):
    """Wraps vaderSentiment — the default, byte-identical-to-legacy provider."""

    def __init__(self) -> None:
        self._vader = SentimentIntensityAnalyzer()

    def score(self, text: str) -> SentimentScore:
        scores = self._vader.polarity_scores(text)
        return {
            "compound": scores["compound"],
            "pos": scores["pos"],
            "neu": scores["neu"],
            "neg": scores["neg"],
        }
