"""Sentiment analysis — composes a pluggable SentimentProvider with provider-independent
label / is_extreme / churn_risk logic. Default provider ('vader') is byte-identical to the
pre-provider-abstraction implementation (see tests/test_sentiment_characterization.py)."""
import re
from typing import Dict, Union

from .sentiment_providers.base import SentimentProvider
from .sentiment_providers.factory import SentimentProviderFactory
from .sentiment_providers.providers.vader import VaderSentimentProvider


class SentimentAnalyzer:
    """Analyzes sentiment of feedback text."""

    def __init__(self, provider: Union[str, SentimentProvider] = "vader"):
        """Initialize sentiment analyzer with a pluggable sentiment provider (default: VADER)."""
        self._provider: SentimentProvider = (
            provider if isinstance(provider, SentimentProvider)
            else SentimentProviderFactory.create(provider)
        )
        self._fallback_provider: SentimentProvider = (
            self._provider if isinstance(self._provider, VaderSentimentProvider)
            else VaderSentimentProvider()
        )

        # Patterns for detecting extreme negativity
        self.extreme_negative_patterns = [
            r'\b(hate|terrible|awful|worst|horrible|useless|garbage|trash)\b',
            r'\b(never\s+(?:using|use|again|works?))\b',
            r'\b(cancel(?:ing|led)?|uninstall(?:ing|ed)?)\b',
            r'\b(unacceptable|disgusting|pathetic)\b',
        ]

        # Patterns for churn risk
        self.churn_patterns = [
            r'\b(going\s+to\s+cancel|will\s+cancel|canceling|switching\s+to)\b',
            r'\b(done\s+with|fed\s+up|had\s+enough)\b',
            r'\b(looking\s+for\s+alternatives|find\s+another)\b',
        ]

    def analyze(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment of text.

        Args:
            text: Feedback text to analyze

        Returns:
            Dict with sentiment scores and classification
        """
        # Get provider scores
        scores = self._provider.score(text)

        # Classify sentiment based on compound score
        compound = scores['compound']
        sentiment_label = self._classify_label(compound)

        # Check for extreme negativity
        is_extreme = self._is_extreme_negative(text)
        has_churn_risk = self._has_churn_indicators(text)

        return {
            'compound': compound,
            'pos': scores['pos'],
            'neu': scores['neu'],
            'neg': scores['neg'],
            'label': sentiment_label,
            'is_extreme': is_extreme,
            'churn_risk': has_churn_risk
        }

    @staticmethod
    def _classify_label(compound: float) -> str:
        """Classify sentiment label from a compound score."""
        if compound >= 0.05:
            return 'positive'
        elif compound <= -0.05:
            return 'negative'
        return 'neutral'

    def _is_extreme_negative(self, text: str) -> bool:
        """Check if text contains extreme negative language."""
        text_lower = text.lower()

        # Check for all caps (yelling)
        if len(text) > 20 and text.isupper():
            return True

        # Check for extreme negative patterns
        for pattern in self.extreme_negative_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True

        # Check for multiple exclamation marks
        if text.count('!') >= 3:
            return True

        return False

    def _has_churn_indicators(self, text: str) -> bool:
        """Check if text indicates customer churn risk."""
        text_lower = text.lower()

        for pattern in self.churn_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True

        return False

    def classify_intensity(self, compound_score: float) -> str:
        """
        Classify sentiment intensity.

        Args:
            compound_score: VADER compound score

        Returns:
            Intensity label
        """
        if compound_score >= 0.5:
            return 'very positive'
        elif compound_score >= 0.05:
            return 'positive'
        elif compound_score <= -0.5:
            return 'very negative'
        elif compound_score <= -0.05:
            return 'negative'
        else:
            return 'neutral'
