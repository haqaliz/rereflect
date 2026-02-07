"""
Tests for notification and alert preference endpoints.
TDD: Written BEFORE implementation (Phase 6→3).
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.models.notification import Notification
from src.models.user_alert_preference import UserAlertPreference
from src.api.auth import hash_password, create_access_token


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_notification(db: Session, user_id: int, org_id: int, **kwargs) -> Notification:
    """Helper to create a notification in the DB."""
    defaults = dict(
        type="urgent_feedback",
        title="Test notification",
        message="Test message body",
        link="/feedbacks/1",
        is_read=False,
        is_dismissed=False,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    defaults.update(kwargs)
    n = Notification(user_id=user_id, organization_id=org_id, **defaults)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _seed_default_prefs(db: Session, user_id: int):
    """Seed default alert preferences for a user (4 types)."""
    types = [
        ("urgent_feedback", None),
        ("sentiment_spike", 50.0),
        ("churn_risk", None),
        ("volume_spike", 2.0),
    ]
    for alert_type, threshold in types:
        pref = UserAlertPreference(
            user_id=user_id,
            alert_type=alert_type,
            is_enabled=True,
            channel_email=False,
            channel_slack=True,
            channel_inapp=True,
            threshold_value=threshold,
        )
        db.add(pref)
    db.commit()


# ── List Notifications ───────────────────────────────────────────────────────

class TestListNotifications:
    """Tests for GET /api/v1/notifications"""

    def test_returns_user_notifications(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should return the current user's notifications."""
        _create_notification(db, test_user.id, test_organization.id, title="Alert 1")
        _create_notification(db, test_user.id, test_organization.id, title="Alert 2")

        response = client.get("/api/v1/notifications", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 2
        assert data["total"] == 2

    def test_excludes_dismissed_notifications(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Dismissed notifications should not appear in the list."""
        _create_notification(db, test_user.id, test_organization.id, title="Visible")
        _create_notification(db, test_user.id, test_organization.id, title="Dismissed", is_dismissed=True)

        response = client.get("/api/v1/notifications", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Visible"

    def test_filters_by_type(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should filter notifications by type query param."""
        _create_notification(db, test_user.id, test_organization.id, type="urgent_feedback")
        _create_notification(db, test_user.id, test_organization.id, type="sentiment_spike")

        response = client.get("/api/v1/notifications?type=urgent_feedback", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["type"] == "urgent_feedback"

    def test_pagination(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should respect page and page_size params."""
        for i in range(5):
            _create_notification(db, test_user.id, test_organization.id, title=f"Alert {i}")

        response = client.get("/api/v1/notifications?page=1&page_size=2", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5

    def test_unauthorized_returns_401(self, client: TestClient):
        """Should return 401 without authentication."""
        response = client.get("/api/v1/notifications")
        assert response.status_code in [401, 403]

    def test_does_not_return_other_users_notifications(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should only return notifications for the authenticated user."""
        other_user = User(
            email="other@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)

        _create_notification(db, test_user.id, test_organization.id, title="Mine")
        _create_notification(db, other_user.id, test_organization.id, title="Theirs")

        response = client.get("/api/v1/notifications", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Mine"


# ── Unread Count ─────────────────────────────────────────────────────────────

class TestUnreadCount:
    """Tests for GET /api/v1/notifications/unread-count"""

    def test_returns_correct_unread_count(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should return the count of unread, non-dismissed notifications."""
        _create_notification(db, test_user.id, test_organization.id, is_read=False)
        _create_notification(db, test_user.id, test_organization.id, is_read=False)
        _create_notification(db, test_user.id, test_organization.id, is_read=True)
        _create_notification(db, test_user.id, test_organization.id, is_read=False, is_dismissed=True)

        response = client.get("/api/v1/notifications/unread-count", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["count"] == 2

    def test_returns_zero_when_no_unread(self, client: TestClient, auth_headers: dict):
        """Should return 0 when user has no unread notifications."""
        response = client.get("/api/v1/notifications/unread-count", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["count"] == 0


# ── Mark Read ────────────────────────────────────────────────────────────────

class TestMarkRead:
    """Tests for PATCH /api/v1/notifications/{id}/read"""

    def test_marks_single_notification_as_read(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should mark a specific notification as read."""
        n = _create_notification(db, test_user.id, test_organization.id)

        response = client.patch(f"/api/v1/notifications/{n.id}/read", headers=auth_headers)

        assert response.status_code == 200
        db.refresh(n)
        assert n.is_read is True

    def test_returns_404_for_other_users_notification(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should not allow marking another user's notification."""
        other_user = User(
            email="other2@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)

        n = _create_notification(db, other_user.id, test_organization.id)

        response = client.patch(f"/api/v1/notifications/{n.id}/read", headers=auth_headers)
        assert response.status_code == 404


# ── Mark All Read ────────────────────────────────────────────────────────────

class TestMarkAllRead:
    """Tests for POST /api/v1/notifications/read-all"""

    def test_marks_all_unread_as_read(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should mark all of the user's unread notifications as read."""
        _create_notification(db, test_user.id, test_organization.id, is_read=False)
        _create_notification(db, test_user.id, test_organization.id, is_read=False)

        response = client.post("/api/v1/notifications/read-all", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["updated"] == 2

        # Verify via unread count
        count_resp = client.get("/api/v1/notifications/unread-count", headers=auth_headers)
        assert count_resp.json()["count"] == 0


# ── Dismiss ──────────────────────────────────────────────────────────────────

class TestDismiss:
    """Tests for PATCH /api/v1/notifications/{id}/dismiss"""

    def test_dismisses_notification(self, client: TestClient, db: Session, test_user: User, test_organization: Organization, auth_headers: dict):
        """Should mark a notification as dismissed."""
        n = _create_notification(db, test_user.id, test_organization.id)

        response = client.patch(f"/api/v1/notifications/{n.id}/dismiss", headers=auth_headers)

        assert response.status_code == 200
        db.refresh(n)
        assert n.is_dismissed is True


# ── Alert Preferences ────────────────────────────────────────────────────────

class TestGetPreferences:
    """Tests for GET /api/v1/notifications/preferences"""

    def test_returns_all_four_alert_types(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Should return preferences for all 4 alert types."""
        _seed_default_prefs(db, test_user.id)

        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "preferences" in data
        assert len(data["preferences"]) == 4
        types = {p["alert_type"] for p in data["preferences"]}
        assert types == {"urgent_feedback", "sentiment_spike", "churn_risk", "volume_spike"}

    def test_returns_empty_list_when_no_prefs_seeded(self, client: TestClient, auth_headers: dict):
        """Should return empty preferences list if none exist."""
        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["preferences"] == []


class TestUpdatePreferences:
    """Tests for PUT /api/v1/notifications/preferences"""

    def test_updates_alert_preferences(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Should update alert preferences in bulk."""
        _seed_default_prefs(db, test_user.id)

        payload = {
            "preferences": [
                {"alert_type": "urgent_feedback", "is_enabled": True, "channel_email": True, "channel_slack": False, "channel_inapp": True, "threshold_value": None},
                {"alert_type": "sentiment_spike", "is_enabled": False, "channel_email": False, "channel_slack": False, "channel_inapp": False, "threshold_value": 75.0},
                {"alert_type": "churn_risk", "is_enabled": True, "channel_email": False, "channel_slack": True, "channel_inapp": True, "threshold_value": None},
                {"alert_type": "volume_spike", "is_enabled": True, "channel_email": False, "channel_slack": True, "channel_inapp": True, "threshold_value": 3.5},
            ]
        }

        response = client.put("/api/v1/notifications/preferences", headers=auth_headers, json=payload)

        assert response.status_code == 200

        # Verify persisted
        prefs = db.query(UserAlertPreference).filter(
            UserAlertPreference.user_id == test_user.id
        ).all()
        urgent = next(p for p in prefs if p.alert_type == "urgent_feedback")
        assert urgent.channel_email is True
        assert urgent.channel_slack is False

        sentiment = next(p for p in prefs if p.alert_type == "sentiment_spike")
        assert sentiment.is_enabled is False
        assert sentiment.threshold_value == 75.0

    def test_rejects_invalid_sentiment_threshold(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Sentiment threshold must be between 0 and 100."""
        _seed_default_prefs(db, test_user.id)

        payload = {
            "preferences": [
                {"alert_type": "sentiment_spike", "is_enabled": True, "channel_email": False, "channel_slack": True, "channel_inapp": True, "threshold_value": 150.0},
            ]
        }

        response = client.put("/api/v1/notifications/preferences", headers=auth_headers, json=payload)
        assert response.status_code == 422

    def test_rejects_invalid_volume_threshold(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Volume threshold must be between 1.0 and 10.0."""
        _seed_default_prefs(db, test_user.id)

        payload = {
            "preferences": [
                {"alert_type": "volume_spike", "is_enabled": True, "channel_email": False, "channel_slack": True, "channel_inapp": True, "threshold_value": 0.5},
            ]
        }

        response = client.put("/api/v1/notifications/preferences", headers=auth_headers, json=payload)
        assert response.status_code == 422


# ── Retention ────────────────────────────────────────────────────────────────

class TestGetRetention:
    """Tests for GET /api/v1/notifications/retention"""

    def test_returns_default_retention(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Should return per-type retention info with defaults."""
        _seed_default_prefs(db, test_user.id)

        response = client.get("/api/v1/notifications/retention", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["min_days"] == 30
        assert data["max_days"] == 365
        assert data["price_per_day"] == 0.10
        assert data["total_extra_days"] == 0
        assert data["total_monthly_cost"] == 0.00
        assert len(data["types"]) == 4


class TestUpdateRetention:
    """Tests for PUT /api/v1/notifications/retention"""

    def test_updates_retention_days(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Should update per-type retention days."""
        _seed_default_prefs(db, test_user.id)

        response = client.put(
            "/api/v1/notifications/retention",
            headers=auth_headers,
            json={"retentions": [{"alert_type": "urgent_feedback", "days": 60}]},
        )

        assert response.status_code == 200
        data = response.json()
        urgent = next(t for t in data["types"] if t["alert_type"] == "urgent_feedback")
        assert urgent["retention_days"] == 60
        assert urgent["extra_days"] == 30
        assert data["total_monthly_cost"] == pytest.approx(30 * 0.10, abs=0.01)

    def test_rejects_below_minimum(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Should reject retention below 30 days."""
        _seed_default_prefs(db, test_user.id)

        response = client.put(
            "/api/v1/notifications/retention",
            headers=auth_headers,
            json={"retentions": [{"alert_type": "urgent_feedback", "days": 10}]},
        )
        assert response.status_code == 422

    def test_rejects_above_maximum(self, client: TestClient, auth_headers: dict):
        """Should reject retention above 365 days."""
        response = client.put(
            "/api/v1/notifications/retention",
            headers=auth_headers,
            json={"retentions": [{"alert_type": "urgent_feedback", "days": 400}]},
        )
        assert response.status_code == 422


# ── Digest Scheduling ───────────────────────────────────────────────────────

class TestDigestScheduling:
    """Tests for digest schedule preferences via PATCH /api/v1/auth/me/preferences"""

    def test_returns_digest_schedule_fields(self, client: TestClient, auth_headers: dict):
        """GET preferences should return digest scheduling fields."""
        response = client.get("/api/v1/auth/me/preferences", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["daily_digest_hour"] == 8
        assert data["weekly_digest_day"] == 1
        assert data["weekly_digest_hour"] == 9

    def test_updates_daily_digest_hour(self, client: TestClient, auth_headers: dict):
        """Should persist daily_digest_hour."""
        response = client.patch(
            "/api/v1/auth/me/preferences",
            headers=auth_headers,
            json={"daily_digest_hour": 10},
        )

        assert response.status_code == 200
        assert response.json()["daily_digest_hour"] == 10

    def test_updates_weekly_digest_day_and_hour(self, client: TestClient, auth_headers: dict):
        """Should persist weekly_digest_day and weekly_digest_hour."""
        response = client.patch(
            "/api/v1/auth/me/preferences",
            headers=auth_headers,
            json={"weekly_digest_day": 4, "weekly_digest_hour": 14},
        )

        assert response.status_code == 200
        assert response.json()["weekly_digest_day"] == 4
        assert response.json()["weekly_digest_hour"] == 14

    def test_rejects_invalid_hour(self, client: TestClient, auth_headers: dict):
        """Should reject hour outside 0-23."""
        response = client.patch(
            "/api/v1/auth/me/preferences",
            headers=auth_headers,
            json={"daily_digest_hour": 25},
        )
        assert response.status_code == 422

    def test_rejects_invalid_day(self, client: TestClient, auth_headers: dict):
        """Should reject day outside 0-6."""
        response = client.patch(
            "/api/v1/auth/me/preferences",
            headers=auth_headers,
            json={"weekly_digest_day": 7},
        )
        assert response.status_code == 422


# ── Per-Type Retention ──────────────────────────────────────────────────────

class TestPerTypeRetention:
    """Tests for per-type retention via preferences and retention endpoints."""

    def test_preference_includes_retention_days(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Preferences response should include retention_days per type."""
        _seed_default_prefs(db, test_user.id)

        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        for pref in response.json()["preferences"]:
            assert "retention_days" in pref
            assert pref["retention_days"] == 30

    def test_updates_retention_per_type(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """PUT /retention should accept per-type retention days."""
        _seed_default_prefs(db, test_user.id)

        response = client.put(
            "/api/v1/notifications/retention",
            headers=auth_headers,
            json={"retentions": [
                {"alert_type": "urgent_feedback", "days": 90},
                {"alert_type": "sentiment_spike", "days": 30},
            ]},
        )

        assert response.status_code == 200
        data = response.json()
        urgent = next(t for t in data["types"] if t["alert_type"] == "urgent_feedback")
        assert urgent["retention_days"] == 90
        assert urgent["extra_days"] == 60

    def test_retention_response_sums_extra_days(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Total extra days should be sum across all types."""
        _seed_default_prefs(db, test_user.id)

        response = client.put(
            "/api/v1/notifications/retention",
            headers=auth_headers,
            json={"retentions": [
                {"alert_type": "urgent_feedback", "days": 90},
                {"alert_type": "sentiment_spike", "days": 180},
            ]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_extra_days"] == 60 + 150  # 210
        assert data["total_monthly_cost"] == pytest.approx(210 * 0.10, abs=0.01)

    def test_retention_get_returns_per_type(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """GET /retention should return per-type breakdown."""
        _seed_default_prefs(db, test_user.id)

        response = client.get("/api/v1/notifications/retention", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "types" in data
        assert len(data["types"]) == 4
        assert data["total_extra_days"] == 0
        assert data["total_monthly_cost"] == 0.0
