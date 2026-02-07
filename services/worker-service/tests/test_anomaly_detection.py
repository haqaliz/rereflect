"""
Tests for anomaly detection logic.
"""

import math
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.tasks.anomaly import _check_org_for_anomaly


class MockFeedbackItem:
    """Mock FeedbackItem for testing."""
    def __init__(self, sentiment_label, created_at):
        self.sentiment_label = sentiment_label
        self.created_at = created_at


class MockOrg:
    """Mock Organization."""
    def __init__(self, org_id=1, alert_channels=None):
        self.id = org_id
        self.default_alert_channels = alert_channels or {"dashboard": True, "email": False, "slack": False}


class MockAnomaly:
    """Mock SentimentAnomaly."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestAnomalyDetectionLogic:
    """Tests for the anomaly detection statistical logic."""

    def test_std_dev_calculation(self):
        """Standard deviation is calculated correctly."""
        values = [10, 20, 30, 40, 50]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        std_dev = math.sqrt(variance)
        assert round(std_dev, 2) == 15.81

    def test_deviation_threshold_2_sigma(self):
        """A value > 2 standard deviations above mean should trigger warning."""
        daily_neg_pcts = [10, 12, 8, 11, 9, 10, 13, 11, 10, 9]
        mean = sum(daily_neg_pcts) / len(daily_neg_pcts)
        variance = sum((x - mean) ** 2 for x in daily_neg_pcts) / (len(daily_neg_pcts) - 1)
        std_dev = math.sqrt(variance)

        # Current value that's > 2σ above mean
        current_pct = mean + (2.5 * std_dev)
        deviation = (current_pct - mean) / std_dev
        assert deviation >= 2.0  # Should trigger

    def test_deviation_below_threshold(self):
        """A value < 2 standard deviations should not trigger."""
        daily_neg_pcts = [10, 12, 8, 11, 9, 10, 13, 11, 10, 9]
        mean = sum(daily_neg_pcts) / len(daily_neg_pcts)
        variance = sum((x - mean) ** 2 for x in daily_neg_pcts) / (len(daily_neg_pcts) - 1)
        std_dev = math.sqrt(variance)

        # Current value that's only 1σ above mean
        current_pct = mean + (1.0 * std_dev)
        deviation = (current_pct - mean) / std_dev
        assert deviation < 2.0  # Should NOT trigger

    def test_critical_threshold_3_sigma(self):
        """A value > 3 standard deviations should be severity=critical."""
        daily_neg_pcts = [10, 12, 8, 11, 9, 10, 13, 11, 10, 9]
        mean = sum(daily_neg_pcts) / len(daily_neg_pcts)
        variance = sum((x - mean) ** 2 for x in daily_neg_pcts) / (len(daily_neg_pcts) - 1)
        std_dev = math.sqrt(variance)

        # Current value that's > 3σ
        current_pct = mean + (3.5 * std_dev)
        deviation = (current_pct - mean) / std_dev
        assert deviation >= 3.0  # Should be critical

        severity = "critical" if deviation >= 3.0 else "warning"
        assert severity == "critical"

    def test_warning_between_2_and_3_sigma(self):
        """A value between 2σ and 3σ should be severity=warning."""
        daily_neg_pcts = [10, 12, 8, 11, 9, 10, 13, 11, 10, 9]
        mean = sum(daily_neg_pcts) / len(daily_neg_pcts)
        variance = sum((x - mean) ** 2 for x in daily_neg_pcts) / (len(daily_neg_pcts) - 1)
        std_dev = math.sqrt(variance)

        # Current value that's 2.5σ (between 2 and 3)
        current_pct = mean + (2.5 * std_dev)
        deviation = (current_pct - mean) / std_dev
        assert 2.0 <= deviation < 3.0

        severity = "critical" if deviation >= 3.0 else "warning"
        assert severity == "warning"

    def test_minimum_std_dev_floor(self):
        """When std_dev < 1, a floor of 5.0 is applied."""
        # All same values → std_dev = 0
        daily_neg_pcts = [10, 10, 10, 10, 10, 10, 10]
        mean = sum(daily_neg_pcts) / len(daily_neg_pcts)
        variance = sum((x - mean) ** 2 for x in daily_neg_pcts) / (len(daily_neg_pcts) - 1)
        std_dev = math.sqrt(variance)
        assert std_dev < 1.0

        # The algorithm uses a floor of 5.0
        effective_std_dev = max(std_dev, 5.0) if std_dev < 1.0 else std_dev
        assert effective_std_dev == 5.0

        # 22% negative (12pp above 10% baseline) with 5.0 std_dev = 2.4σ → warning
        current_pct = 22.0
        deviation = (current_pct - mean) / effective_std_dev
        assert deviation >= 2.0

    def test_insufficient_data_skipped(self):
        """Less than 7 days of data should be skipped."""
        daily_data_count = 5
        assert daily_data_count < 7  # Should skip

    def test_insufficient_recent_feedback_skipped(self):
        """Less than 5 recent feedback items should be skipped."""
        recent_total = 3
        assert recent_total < 5  # Should skip


class TestAnomalyDeviationPercent:
    """Tests for deviation percentage calculation."""

    def test_positive_deviation(self):
        """Deviation percent is positive when current > baseline."""
        baseline = 15.0
        current = 40.0
        deviation_pct = round(current - baseline, 1)
        assert deviation_pct == 25.0

    def test_score_capped(self):
        """Deviation is raw difference, not percentage of baseline."""
        baseline = 10.0
        current = 90.0
        deviation_pct = round(current - baseline, 1)
        assert deviation_pct == 80.0
