"""Tests for sentiment analyzer."""
import pytest
from src.analyzer.sentiment import SentimentAnalyzer


@pytest.fixture
def analyzer():
    """Create sentiment analyzer instance."""
    return SentimentAnalyzer()


def test_positive_sentiment(analyzer):
    """Test positive sentiment detection."""
    text = "Love the new interface! Great features and excellent design."
    result = analyzer.analyze(text)

    assert result['label'] == 'positive'
    assert result['compound'] > 0


def test_negative_sentiment(analyzer):
    """Test negative sentiment detection."""
    text = "Terrible app. Crashes constantly and horrible performance."
    result = analyzer.analyze(text)

    assert result['label'] == 'negative'
    assert result['compound'] < 0


def test_neutral_sentiment(analyzer):
    """Test neutral sentiment detection."""
    text = "The app has a button for settings."
    result = analyzer.analyze(text)

    assert result['label'] == 'neutral'


def test_extreme_negative_detection(analyzer):
    """Test extreme negative language detection."""
    text = "THIS IS TERRIBLE!!! I HATE THIS APP!!!"
    result = analyzer.analyze(text)

    assert result['is_extreme'] is True
    assert result['label'] == 'negative'


def test_churn_risk_detection(analyzer):
    """Test churn risk detection."""
    text = "I'm going to cancel my subscription if this isn't fixed."
    result = analyzer.analyze(text)

    assert result['churn_risk'] is True


def test_all_caps_extreme(analyzer):
    """Test all-caps text is marked as extreme."""
    text = "THIS APP IS COMPLETELY BROKEN AND UNUSABLE"
    result = analyzer.analyze(text)

    assert result['is_extreme'] is True


def test_intensity_classification(analyzer):
    """Test sentiment intensity classification."""
    assert analyzer.classify_intensity(0.7) == 'very positive'
    assert analyzer.classify_intensity(0.2) == 'positive'
    assert analyzer.classify_intensity(0.0) == 'neutral'
    assert analyzer.classify_intensity(-0.2) == 'negative'
    assert analyzer.classify_intensity(-0.7) == 'very negative'
