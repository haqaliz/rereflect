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
    # Create 10 days of historical data, ~10% negative per day
    for day_offset in range(2, 12):  # days 2-11 ago (avoid last 24h)
        day = now - timedelta(days=day_offset)
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
                created_at=now - timedelta(hours=1, minutes=i),
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
                created_at=now - timedelta(hours=1, minutes=i),
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
        # Add 10 recent items with 90% negative (vs ~10% baseline)
        for i in range(10):
            sentiment = "negative" if i < 9 else "positive"
            db.add(FeedbackItem(
                organization_id=org_with_baseline.id,
                text=f"Recent extreme {i}",
                source="manual",
                sentiment_label=sentiment,
                sentiment_score=-0.8 if sentiment == "negative" else 0.5,
                created_at=now - timedelta(hours=1, minutes=i),
            ))
        db.commit()

        with patch("src.tasks.anomaly._dispatch_anomaly_alerts"):
            result = _check_org_for_anomaly(db, org_with_baseline)
        assert result is True
        db.flush()

        anomaly = db.query(SentimentAnomaly).filter(
            SentimentAnomaly.organization_id == org_with_baseline.id,
        ).first()
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
                created_at=now - timedelta(hours=1, minutes=i),
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
                created_at=now - timedelta(hours=1, minutes=i),
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
                created_at=now - timedelta(hours=1, minutes=i),
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
                created_at=now - timedelta(hours=1, minutes=i),
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
    """Tests for _dispatch_anomaly_alerts routing."""

    def test_sends_email_when_user_has_email_enabled(self, db, org_with_user):
        """Should send email when user has email alert channel enabled."""
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org, user = org_with_user
        anomaly = MagicMock(
            severity="warning",
            current_negative_pct=40.0,
            baseline_negative_pct=10.0,
            deviation_pct=30.0,
            feedback_count=10,
        )

        with patch("src.tasks.anomaly._send_anomaly_email") as mock_email:
            _dispatch_anomaly_alerts(db, org, anomaly)
            mock_email.assert_called_once_with(user.email, org.name, anomaly)

    def test_skips_email_when_user_has_email_disabled(self, db):
        """Should not send email when user has email channel disabled."""
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org = Organization(
            name="No Email Corp", plan="pro",
            default_alert_channels={"dashboard": True, "email": False, "slack": False},
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        user = User(
            email="noemail@test.com",
            organization_id=org.id,
            role="owner",
            alert_channels={"dashboard": True, "email": False, "slack": False},
        )
        db.add(user)
        db.commit()

        anomaly = MagicMock()

        with patch("src.tasks.anomaly._send_anomaly_email") as mock_email:
            _dispatch_anomaly_alerts(db, org, anomaly)
            mock_email.assert_not_called()

    def test_uses_org_defaults_when_user_has_no_override(self, db):
        """Should use org default_alert_channels when user.alert_channels is None."""
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org = Organization(
            name="Default Alert Corp", plan="pro",
            default_alert_channels={"dashboard": True, "email": True, "slack": False},
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        user = User(
            email="default@test.com",
            organization_id=org.id,
            role="owner",
            alert_channels=None,  # No user override
        )
        db.add(user)
        db.commit()

        anomaly = MagicMock(
            severity="warning",
            current_negative_pct=40.0,
            baseline_negative_pct=10.0,
            deviation_pct=30.0,
            feedback_count=10,
        )

        with patch("src.tasks.anomaly._send_anomaly_email") as mock_email:
            _dispatch_anomaly_alerts(db, org, anomaly)
            # Should send because org default has email=True
            mock_email.assert_called_once()

    def test_sends_slack_when_org_has_slack_enabled(self, db):
        """Should send Slack alert when org default has slack enabled."""
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org = Organization(
            name="Slack Corp", plan="pro",
            default_alert_channels={"dashboard": True, "email": False, "slack": True},
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        anomaly = MagicMock()

        with patch("src.tasks.anomaly._send_anomaly_slack") as mock_slack:
            _dispatch_anomaly_alerts(db, org, anomaly)
            mock_slack.assert_called_once_with(db, org, anomaly)

    def test_skips_slack_when_org_has_slack_disabled(self, db):
        """Should not send Slack when org default has slack disabled."""
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org = Organization(
            name="No Slack Corp", plan="pro",
            default_alert_channels={"dashboard": True, "email": False, "slack": False},
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        anomaly = MagicMock()

        with patch("src.tasks.anomaly._send_anomaly_slack") as mock_slack:
            _dispatch_anomaly_alerts(db, org, anomaly)
            mock_slack.assert_not_called()

    def test_handles_email_failure_gracefully(self, db, org_with_user):
        """Should log error but not crash when email sending fails."""
        from src.tasks.anomaly import _dispatch_anomaly_alerts

        org, user = org_with_user
        anomaly = MagicMock(severity="critical")

        with patch("src.tasks.anomaly._send_anomaly_email", side_effect=Exception("SMTP error")):
            # Should not raise
            _dispatch_anomaly_alerts(db, org, anomaly)


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
