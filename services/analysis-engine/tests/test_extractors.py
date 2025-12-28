"""Tests for extractors."""
import pytest
from src.analyzer.extractors import PainPointExtractor, FeatureRequestExtractor


@pytest.fixture
def pain_point_extractor():
    """Create pain point extractor."""
    return PainPointExtractor()


@pytest.fixture
def feature_request_extractor():
    """Create feature request extractor."""
    return FeatureRequestExtractor()


def test_complaint_detection(pain_point_extractor):
    """Test complaint detection."""
    feedback_items = [
        {
            'id': '1',
            'text': 'The app crashes every time I upload a file.',
            'sentiment': {'label': 'negative', 'compound': -0.6}
        },
        {
            'id': '2',
            'text': 'Great app! Works perfectly.',
            'sentiment': {'label': 'positive', 'compound': 0.7}
        }
    ]

    result = pain_point_extractor.extract(feedback_items)

    # Should only extract the complaint
    assert len(result) > 0
    assert result[0]['count'] >= 1


def test_pain_point_clustering(pain_point_extractor):
    """Test clustering of similar pain points."""
    feedback_items = [
        {
            'id': '1',
            'text': 'App crashes when uploading files',
            'sentiment': {'label': 'negative', 'compound': -0.6}
        },
        {
            'id': '2',
            'text': 'Crash on file upload',
            'sentiment': {'label': 'negative', 'compound': -0.5}
        },
        {
            'id': '3',
            'text': 'Upload feature makes the app crash',
            'sentiment': {'label': 'negative', 'compound': -0.7}
        }
    ]

    result = pain_point_extractor.extract(feedback_items)

    # Similar complaints should be extracted
    assert len(result) > 0
    # Total count across all clusters should match input
    total_count = sum(pp['count'] for pp in result)
    assert total_count == 3


def test_feature_request_detection(feature_request_extractor):
    """Test feature request detection."""
    feedback_items = [
        {
            'id': '1',
            'text': 'I wish there was a dark mode option.',
            'sentiment': {'label': 'neutral', 'compound': 0.1}
        },
        {
            'id': '2',
            'text': 'Please add Slack integration.',
            'sentiment': {'label': 'neutral', 'compound': 0.0}
        }
    ]

    result = feature_request_extractor.extract(feedback_items)

    assert len(result) >= 2


def test_feature_request_clustering(feature_request_extractor):
    """Test clustering of similar feature requests."""
    feedback_items = [
        {
            'id': '1',
            'text': 'Would love to see dark mode',
            'sentiment': {'label': 'positive', 'compound': 0.3}
        },
        {
            'id': '2',
            'text': 'Please add a dark theme option',
            'sentiment': {'label': 'neutral', 'compound': 0.0}
        },
        {
            'id': '3',
            'text': 'I wish there was a dark mode feature',
            'sentiment': {'label': 'neutral', 'compound': 0.0}
        }
    ]

    result = feature_request_extractor.extract(feedback_items)

    # Similar requests should be extracted
    assert len(result) > 0
    # Total count across all requests should match detected requests
    total_count = sum(fr['count'] for fr in result)
    assert total_count >= 2  # At least 2 should be detected


def test_empty_feedback(pain_point_extractor, feature_request_extractor):
    """Test handling of empty feedback."""
    empty_feedback = []

    pain_points = pain_point_extractor.extract(empty_feedback)
    feature_requests = feature_request_extractor.extract(empty_feedback)

    assert pain_points == []
    assert feature_requests == []
