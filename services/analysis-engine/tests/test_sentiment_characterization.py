"""Characterization test — pins SentimentAnalyzer().analyze()'s exact output for a fixed set of
inputs, against the pre-refactor sentiment.py. This is the load-bearing safety net for the
sentiment-provider-core refactor: after the provider seam is extracted (Phase 3), this test must
still pass UNMODIFIED. If it goes red, the refactor introduced a behavior change and is wrong —
fix the code, never this file.

Expected values below were captured by running SentimentAnalyzer().analyze() against today's
(pre-refactor) sentiment.py and hardcoding the actual observed output — they are not
independently computed/theoretical VADER values.
"""
import pytest

from src.analyzer.sentiment import SentimentAnalyzer

EXPECTED_KEY_ORDER = ['compound', 'pos', 'neu', 'neg', 'label', 'is_extreme', 'churn_risk']

# (input text, expected result dict) — positive, negative, neutral, extreme-negative (all-caps +
# hate pattern), churn-risk, mild-positive/negation edge case, emoji.
CASES = [
    (
        'Love the new interface! Great features and excellent design.',
        {
            'compound': 0.923, 'pos': 0.672, 'neu': 0.328, 'neg': 0.0,
            'label': 'positive', 'is_extreme': False, 'churn_risk': False,
        },
    ),
    (
        'Terrible app. Crashes constantly and horrible performance.',
        {
            'compound': -0.765, 'pos': 0.0, 'neu': 0.431, 'neg': 0.569,
            'label': 'negative', 'is_extreme': True, 'churn_risk': False,
        },
    ),
    (
        'The app has a button for settings.',
        {
            'compound': 0.0, 'pos': 0.0, 'neu': 1.0, 'neg': 0.0,
            'label': 'neutral', 'is_extreme': False, 'churn_risk': False,
        },
    ),
    (
        'THIS IS TERRIBLE!!! I HATE THIS APP!!!',
        {
            'compound': -0.8388, 'pos': 0.0, 'neu': 0.386, 'neg': 0.614,
            'label': 'negative', 'is_extreme': True, 'churn_risk': False,
        },
    ),
    (
        "I'm going to cancel my subscription if this isn't fixed.",
        {
            'compound': -0.25, 'pos': 0.0, 'neu': 0.818, 'neg': 0.182,
            'label': 'negative', 'is_extreme': True, 'churn_risk': True,
        },
    ),
    (
        'Not bad, could be better though.',
        {
            'compound': 0.6956, 'pos': 0.59, 'neu': 0.41, 'neg': 0.0,
            'label': 'positive', 'is_extreme': False, 'churn_risk': False,
        },
    ),
    (
        'Great job team! 🎉 Really love the emoji support 😍',
        {
            'compound': 0.9537, 'pos': 0.658, 'neu': 0.342, 'neg': 0.0,
            'label': 'positive', 'is_extreme': False, 'churn_risk': False,
        },
    ),
]


@pytest.fixture
def analyzer():
    return SentimentAnalyzer()


@pytest.mark.parametrize('text,expected', CASES)
def test_analyze_output_is_byte_stable(analyzer, text, expected):
    result = analyzer.analyze(text)

    assert list(result.keys()) == EXPECTED_KEY_ORDER

    assert result['compound'] == pytest.approx(expected['compound'])
    assert result['pos'] == pytest.approx(expected['pos'])
    assert result['neu'] == pytest.approx(expected['neu'])
    assert result['neg'] == pytest.approx(expected['neg'])
    assert result['label'] == expected['label']
    assert result['is_extreme'] is expected['is_extreme']
    assert result['churn_risk'] is expected['churn_risk']
