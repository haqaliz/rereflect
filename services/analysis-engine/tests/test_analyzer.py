"""Tests for the main analyzer."""
import pytest
from src.analyzer import FeedbackAnalyzer, FeedbackInput, FeedbackItem


@pytest.fixture
def analyzer():
    """Create analyzer instance."""
    return FeedbackAnalyzer(enable_clustering=False)


@pytest.fixture
def sample_feedback():
    """Create sample feedback data."""
    return FeedbackInput(feedback=[
        FeedbackItem(
            id="1",
            text="The app crashes when I upload files. Very frustrating!",
            date="2025-11-10",
            source="support_ticket"
        ),
        FeedbackItem(
            id="2",
            text="Would love to see a dark mode option.",
            date="2025-11-11",
            source="feature_request"
        ),
        FeedbackItem(
            id="3",
            text="Great app! Love the new features.",
            date="2025-11-12",
            source="app_review"
        ),
        FeedbackItem(
            id="4",
            text="Terrible performance. App is too slow.",
            date="2025-11-13",
            source="app_review"
        ),
        FeedbackItem(
            id="5",
            text="I'm canceling if you don't fix the login issues!",
            date="2025-11-14",
            source="support_ticket"
        )
    ])


def test_complete_analysis(analyzer, sample_feedback):
    """Test complete analysis workflow."""
    result = analyzer.analyze(sample_feedback)

    assert result.total_feedback_count == 5
    assert result.sentiment_summary is not None
    assert isinstance(result.common_pain_points, list)
    assert isinstance(result.feature_requests, list)
    assert isinstance(result.urgent_feedback, list)


def test_sentiment_summary(analyzer, sample_feedback):
    """Test sentiment summary generation."""
    result = analyzer.analyze(sample_feedback)

    summary = result.sentiment_summary

    # Check percentages add up to 100
    total = summary.positive_percent + summary.neutral_percent + summary.negative_percent
    assert abs(total - 100.0) < 0.1  # Allow small floating point error

    # Should have some negative feedback
    assert summary.negative_percent > 0


def test_pain_point_extraction(analyzer, sample_feedback):
    """Test pain point extraction."""
    result = analyzer.analyze(sample_feedback)

    # Should find at least one pain point
    assert len(result.common_pain_points) > 0

    # Check structure
    for pp in result.common_pain_points:
        assert pp.issue
        assert pp.count > 0
        assert isinstance(pp.examples, list)


def test_feature_request_extraction(analyzer, sample_feedback):
    """Test feature request extraction."""
    result = analyzer.analyze(sample_feedback)

    # Should find the dark mode request
    assert len(result.feature_requests) > 0

    # Check structure
    for fr in result.feature_requests:
        assert fr.feature
        assert fr.count > 0
        assert isinstance(fr.examples, list)


def test_urgent_feedback_flagging(analyzer, sample_feedback):
    """Test urgent feedback flagging."""
    result = analyzer.analyze(sample_feedback)

    # Should flag the cancellation threat as urgent
    assert len(result.urgent_feedback) > 0

    # Check structure
    for urgent in result.urgent_feedback:
        assert urgent.id
        assert urgent.issue
        assert urgent.reason
        assert urgent.sentiment


def test_empty_feedback(analyzer):
    """Test handling of empty feedback."""
    empty_input = FeedbackInput(feedback=[])

    result = analyzer.analyze(empty_input)

    assert result.total_feedback_count == 0
    assert result.analysis_notes is not None
    assert len(result.common_pain_points) == 0
    assert len(result.feature_requests) == 0


def test_small_dataset_warning(analyzer):
    """Test warning for small datasets."""
    small_feedback = FeedbackInput(feedback=[
        FeedbackItem(
            id="1",
            text="Test feedback",
            date="2025-11-10",
            source="test"
        )
    ])

    result = analyzer.analyze(small_feedback)

    # Should have a warning note
    assert result.analysis_notes is not None
    assert "small dataset" in result.analysis_notes.lower()


def test_sentiment_trend(analyzer):
    """Test sentiment trend calculation."""
    feedback = FeedbackInput(feedback=[
        FeedbackItem(
            id="1",
            text="Bad app",
            date="2025-10-10",
            source="test"
        ),
        FeedbackItem(
            id="2",
            text="Great app",
            date="2025-11-10",
            source="test"
        ),
        FeedbackItem(
            id="3",
            text="Okay app",
            date="2025-11-15",
            source="test"
        )
    ])

    result = analyzer.analyze(feedback)

    # Should have trend data
    assert len(result.sentiment_summary.trend_by_month) > 0
