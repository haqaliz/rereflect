"""
Integration tests for anomaly detection with real SQLite database.
Tests _check_org_for_anomaly, _dispatch_anomaly_alerts, detect_sentiment_anomalies.
"""

import math
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from src.models import (
    Organization, User, FeedbackItem, SentimentAnomaly, Integration,
)

def recent_ts(now, i):
    """A timestamp inside the last 24h that is guaranteed to share `now`'s date.

    The detector mixes two notions of time: a rolling 24-hour window for the
    "current" numbers, and calendar-date buckets (func.date) for the baseline.
    Placing recent items at `now - 1h - i minutes` straddles midnight whenever
    `now` is just past 01:00, which splits them across two date buckets, inflates
    the baseline's standard deviation, and drops the deviation under the 2σ
    detection floor — so these tests failed only when CI happened to run in that
    window. Clamping to today keeps the recent items in one bucket at any hour.
    """
    base = now.replace(second=0, microsecond=0) - timedelta(minutes=30)
    if base.date() != now.date():
        base = now.replace(hour=0, minute=1, second=0, microsecond=0)
    return base + timedelta(seconds=i)



@pytest.fixture
def org_with_baseline(db):
    """Create an org with 10 days of baseline feedback (10% negative rate)."""
    org = Organization(
        name="Baseline Corp", plan="pro",
        default_alert_channels={"dashboard": True, "email": False, "slack": False},
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    now = datetime.utcnow()
    # Create 10 days of historical data, ~10% negative per day.
    # Anchor each day to midnight: the detector groups by func.date(created_at),
    # so `day + i hours` off a wall-clock `now` silently splits one logical day
    # across two date buckets whenever now's hour + 9 crosses midnight. That made
    # the whole class pass or fail depending on the time of day it ran.
    for day_offset in range(2, 12):  # days 2-11 ago (avoid last 24h)
        day = (now - timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for i in range(10):
            sentiment = "negative" if i == 0 else "positive"
            db.add(FeedbackItem(
                organization_id=org.id,
                text=f"Day {day_offset} feedback {i}",
                source="manual",
                sentiment_label=sentiment,
                sentiment_score=-0.5 if sentiment == "negative" else 0.5,
                created_at=day + timedelta(hours=i),
            ))
    db.commit()
    return org


@pytest.fixture
def org_with_user(db, org_with_baseline):
    """Add a user to the org for alert dispatch tests."""
    user = User(
        email="alert@test.com",
        organization_id=org_with_baseline.id,
        role="owner",
        alert_channels={"dashboard": True, "email": True, "slack": False},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return org_with_baseline, user


class TestCheckOrgForAnomalyIntegration:
    """Integration tests for _check_org_for_anomaly with real DB."""

    def test_no_anomaly_when_recent_data_is_normal(self, db, org_with_baseline):
        """No anomaly created when recent negative rate is within normal range."""
        from src.tasks.anomaly import _check_org_for_anomaly

        now = datetime.utcnow()
        # Add 10 recent items with 10% negative (matches baseline)
        for i in range(10):
            sentiment = "negative" if i == 0 else "positive"
            db.add(FeedbackItem(
                organization_id=org_with_baseline.id,
                text=f"Recent normal {i}",
                source="manual",
                sentiment_label=sentiment,
                sentiment_score=-0.5 if sentiment == "negative" else 0.5,
                created_at=recent_ts(now, i),
            ))
        db.commit()

        result = _check_org_for_anomaly(db, org_with_baseline)
        assert result is False

    def test_creates_warning_anomaly_on_spike(self, db, org_with_baseline):
        """Should create a warning anomaly when negative rate spikes above 2σ."""
        from src.tasks.anomaly import _check_org_for_anomaly

        now = datetime.utcnow()
        # Add 10 recent items with 50% negative (vs ~10% baseline)
        for i in range(10):
            sentiment = "negative" if i < 5 else "positive"
            db.add(FeedbackItem(
                organization_id=org_with_baseline.id,
                text=f"Recent spike {i}",
                source="manual",
                sentiment_label=sentiment,
                sentiment_score=-0.5 if sentiment == "negative" else 0.5,
                created_at=recent_ts(now, i),
            ))
        db.commit()

        with patch("src.tasks.anomaly._dispatch_anomaly_alerts"):
            result = _check_org_for_anomaly(db, org_with_baseline)
        assert result is True
        db.flush()

        # Verify anomaly was created
        anomaly = db.query(SentimentAnomaly).filter(
            SentimentAnomaly.organization_id == org_with_baseline.id,
        ).first()
        assert anomaly is not None
        assert anomaly.anomaly_type == "negative_spike"
        assert anomaly.severity in ("warning", "critical")
        assert anomaly.current_negative_pct == 50.0
        assert anomaly.is_resolved is False

    def test_creates_critical_anomaly_on_extreme_spike(self, db, org_with_baseline):
        """Should create critical anomaly when negative rate massively spikes (>3σ)."""
        from src.tasks.anomaly import _check_org_for_anomaly

        now = datetime.utcnow()

        # The 30-day baseline query has no upper bound (anomaly.py:92), so the
        # spike day is folded into its own baseline. With only 10 baseline days a
        # single 90%-negative outlier drags the mean and std_dev up far enough
        # that the deviation lands at ~3.0σ — right on the critical boundary.
        # Extend the baseline so the outlier is properly diluted and the spike is
        # unambiguously >3σ.
        for day_offset in range(12, 30):
            day = (now - timedelta(days=day_offset)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            for i in range(10):
                sentiment = "negative" if i == 0 else "positive"
                db.add(FeedbackItem(
                    organization_id=org_with_baseline.id,
                    text=f"Extended baseline {day_offset}-{i}",
                    source="manual",
                    sentiment_label=sentiment,
                    sentiment_score=-0.8 if sentiment == "negative" else 0.5,
                    created_at=day,
                ))
        db.commit()

        # Add 10 recent items, all negative (vs ~10% baseline)
        for i in range(10):
            sentiment = "negative"
            db.add(FeedbackItem(
                organization_id=org_with_baseline.id,
                text=f"Recent extreme {i}",
                source="manual",
                sentiment_label=sentiment,
                sentiment_score=-0.8 if sentiment == "negative" else 0.5,
                created_at=recent_ts(now, i),
            ))
        db.commit()

        with patch("src.tasks.anomaly._dispatch_anomaly_alerts"):
            result = _check_org_for_anomaly(db, org_with_baseline)
        assert result is True
        db.flush()

        # Order explicitly — an unordered .first() can return an anomaly left by an
        # earlier test in this class rather than the one this test just triggered.
        anomaly = db.query(SentimentAnomaly).filter(
            SentimentAnomaly.organization_id == org_with_baseline.id,
        ).order_by(SentimentAnomaly.id.desc()).first()
        assert anomaly is not None
        assert anomaly.severity == "critical"

    def test_skips_when_unresolved_anomaly_exists(self, db, org_with_baseline):
        """Should skip if there's already an unresolved anomaly within 24h."""
        from src.tasks.anomaly import _check_org_for_anomaly

        # Create an existing unresolved anomaly
        db.add(SentimentAnomaly(
            organization_id=org_with_baseline.id,
            detected_at=datetime.utcnow() - timedelta(hours=2),
            anomaly_type="negative_spike",
            severity="warning",
            baseline_negative_pct=10.0,
            current_negative_pct=40.0,
            deviation_pct=30.0,
            time_window_hours=24,
            feedback_count=10,
            is_resolved=False,
        ))
        db.commit()

        now = datetime.utcnow()
        # Add spike data
        for i in range(10):
            sentiment = "negative" if i < 8 else "positive"
            db.add(FeedbackItem(
                organization_id=org_with_baseline.id,
                text=f"Spike again {i}",
                source="manual",
                sentiment_label=sentiment,
                sentiment_score=-0.5 if sentiment == "negative" else 0.5,
                created_at=recent_ts(now, i),
            ))
        db.commit()

        result = _check_org_for_anomaly(db, org_with_baseline)
        assert result is False

    def test_detects_after_resolved_anomaly(self, db, org_with_baseline):
        """Should detect new anomaly if previous one was resolved."""
        from src.tasks.anomaly import _check_org_for_anomaly

        # Create a resolved anomaly
        db.add(SentimentAnomaly(
            organization_id=org_with_baseline.id,
            detected_at=datetime.utcnow() - timedelta(hours=2),
            anomaly_type="negative_spike",
            severity="warning",
            baseline_negative_pct=10.0,
            current_negative_pct=40.0,
            deviation_pct=30.0,
            time_window_hours=24,
            feedback_count=10,
            is_resolved=True,
            resolved_at=datetime.utcnow() - timedelta(hours=1),
        ))
        db.commit()

        now = datetime.utcnow()
        # Add spike data
        for i in range(10):
            sentiment = "negative" if i < 7 else "positive"
            db.add(FeedbackItem(
                organization_id=org_with_baseline.id,
                text=f"New spike {i}",
                source="manual",
                sentiment_label=sentiment,
                sentiment_score=-0.5 if sentiment == "negative" else 0.5,
                created_at=recent_ts(now, i),
            ))
        db.commit()

        with patch("src.tasks.anomaly._dispatch_anomaly_alerts"):
            result = _check_org_for_anomaly(db, org_with_baseline)
        assert result is True

    def test_skips_with_insufficient_baseline_days(self, db):
        """Should skip when org has fewer than 7 days of data."""
        from src.tasks.anomaly import _check_org_for_anomaly

        org = Organization(name="New Corp", plan="free")
        db.add(org)
        db.commit()
        db.refresh(org)

        now = datetime.utcnow()
        # Only 3 days of data
        for day_offset in range(2, 5):
            day = now - timedelta(days=day_offset)
            for i in range(10):
                db.add(FeedbackItem(
                    organization_id=org.id,
                    text=f"Day {day_offset} item {i}",
                    source="manual",
                    sentiment_label="negative" if i < 3 else "positive",
                    sentiment_score=-0.5 if i < 3 else 0.5,
                    created_at=day + timedelta(hours=i),
                ))
        db.commit()

        result = _check_org_for_anomaly(db, org)
        assert result is False

    def test_skips_with_too_few_recent_items(self, db, org_with_baseline):
        """Should skip when fewer than 5 items in last 24h."""
        from src.tasks.anomaly import _check_org_for_anomaly

        now = datetime.utcnow()
        # Only 3 recent items
        for i in range(3):
            db.add(FeedbackItem(
                organization_id=org_with_baseline.id,
                text=f"Too few {i}",
                source="manual",
                sentiment_label="negative",
                sentiment_score=-0.8,
                created_at=recent_ts(now, i),
            ))
        db.commit()

        result = _check_org_for_anomaly(db, org_with_baseline)
        assert result is False

    def test_anomaly_stores_correct_deviation_pct(self, db, org_with_baseline):
        """Anomaly deviation_pct should be current - baseline."""
        from src.tasks.anomaly import _check_org_for_anomaly

        now = datetime.utcnow()
        # 60% negative recent data
        for i in range(10):
            sentiment = "negative" if i < 6 else "positive"
            db.add(FeedbackItem(
                organization_id=org_with_baseline.id,
                text=f"Deviation test {i}",
                source="manual",
                sentiment_label=sentiment,
                sentiment_score=-0.5 if sentiment == "negative" else 0.5,
                created_at=recent_ts(now, i),
            ))
        db.commit()

        with patch("src.tasks.anomaly._dispatch_anomaly_alerts"):
            _check_org_for_anomaly(db, org_with_baseline)
        db.flush()

        anomaly = db.query(SentimentAnomaly).filter(
            SentimentAnomaly.organization_id == org_with_baseline.id,
        ).first()
        assert anomaly is not None
        # 60% current - ~10% baseline ≈ 50pp deviation
        assert anomaly.deviation_pct > 40.0


class TestDispatchAnomalyAlerts:
    """_dispatch_anomaly_alerts delegates routing to the notification dispatcher.

    This class used to assert per-user channel fan-out (email on/off, Slack on/off,
    org defaults vs user overrides) by patching the old anomaly senders. That routing
    moved into notification_dispatch.dispatch_alert,
    which resolves each user's preferences and — for email — queues a daily digest
    rather than sending immediately. _dispatch_anomaly_alerts no longer calls those
    helpers at all, so the old assertions could never pass. Channel routing is
    covered where it now lives; what remains this function's job is building a
    correct alert payload and handing it over.
    """

    def _anomaly(self, severity="warning"):
        return MagicMock(
            id=123,
            severity=severity,
            current_negative_pct=40.0,
            baseline_negative_pct=10.0,
            deviation_pct=30.0,
            feedback_count=10,
        )

    def test_delegates_to_dispatch_alert_with_org_and_alert_type(self, db, org_with_user):
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org, _user = org_with_user

        with patch("src.notification_dispatch.dispatch_alert") as mock_dispatch:
            _dispatch_anomaly_alerts(db, org, self._anomaly())

        mock_dispatch.assert_called_once()
        kwargs = mock_dispatch.call_args.kwargs
        assert kwargs["org_id"] == org.id
        assert kwargs["alert_type"] == "sentiment_spike"
        assert kwargs["link"] == "/dashboard"

    def test_title_and_message_carry_the_anomaly_numbers(self, db, org_with_user):
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org, _user = org_with_user

        with patch("src.notification_dispatch.dispatch_alert") as mock_dispatch:
            _dispatch_anomaly_alerts(db, org, self._anomaly(severity="critical"))

        kwargs = mock_dispatch.call_args.kwargs
        assert "CRITICAL" in kwargs["title"]
        assert "40% negative" in kwargs["title"]
        assert "baseline: 10%" in kwargs["message"]
        assert "+30pp" in kwargs["message"]
        assert "10 feedback items" in kwargs["message"]

    def test_metadata_carries_severity_and_percentages(self, db, org_with_user):
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org, _user = org_with_user

        with patch("src.notification_dispatch.dispatch_alert") as mock_dispatch:
            _dispatch_anomaly_alerts(db, org, self._anomaly())

        metadata = mock_dispatch.call_args.kwargs["metadata"]
        assert metadata["anomaly_id"] == 123
        assert metadata["severity"] == "warning"
        assert metadata["current_negative_pct"] == 40.0
        assert metadata["baseline_negative_pct"] == 10.0



class TestDetectSentimentAnomaliesTask:
    """Tests for the top-level detect_sentiment_anomalies Celery task."""

    def test_returns_no_organizations_when_empty(self, db):
        """Should return no_organizations status when no orgs exist."""
        from src.tasks.anomaly import detect_sentiment_anomalies

        with patch("src.tasks.anomaly.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = detect_sentiment_anomalies()

        assert result["status"] == "no_organizations"
        assert result["anomalies_created"] == 0

    def test_checks_all_organizations(self, db, org_with_baseline):
        """Should check each org and return correct counts."""
        from src.tasks.anomaly import detect_sentiment_anomalies

        # Add another org
        org2 = Organization(name="Corp 2", plan="free")
        db.add(org2)
        db.commit()

        with patch("src.tasks.anomaly.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = detect_sentiment_anomalies()

        assert result["status"] == "complete"
        assert result["orgs_checked"] == 2

    def test_handles_org_check_error_gracefully(self, db):
        """Should handle errors in individual org checks without crashing."""
        from src.tasks.anomaly import detect_sentiment_anomalies

        org = Organization(name="Error Corp", plan="free")
        db.add(org)
        db.commit()

        with patch("src.tasks.anomaly.get_db_session") as mock_ctx, \
             patch("src.tasks.anomaly._check_org_for_anomaly", side_effect=Exception("DB error")):
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = detect_sentiment_anomalies()

        # Should still complete, just 0 orgs_checked (error during check)
        assert result["status"] == "complete"
        assert result["anomalies_created"] == 0
