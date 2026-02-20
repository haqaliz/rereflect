"""
TDD tests for Phase 2: Preferences API extension for customer_health_drop.
RED → GREEN → REFACTOR.

Tests for GET/PUT /api/v1/notifications/preferences handling of
the customer_health_drop alert type with dual thresholds.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.models.user_alert_preference import UserAlertPreference


# ---------------------------------------------------------------------------
# GET /api/v1/notifications/preferences
# ---------------------------------------------------------------------------

class TestGetPreferencesHealthDrop:
    """GET /api/v1/notifications/preferences returns customer_health_drop with defaults."""

    def test_get_preferences_includes_customer_health_drop_type(
        self, client: TestClient, auth_headers: dict
    ):
        """customer_health_drop must appear in the preferences list."""
        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        alert_types = [p["alert_type"] for p in data["preferences"]]
        assert "customer_health_drop" in alert_types

    def test_get_preferences_health_drop_returns_default_threshold_50(
        self, client: TestClient, auth_headers: dict
    ):
        """When no pref record exists, threshold_value defaults to 50."""
        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        prefs = response.json()["preferences"]
        health_pref = next(
            (p for p in prefs if p["alert_type"] == "customer_health_drop"), None
        )
        assert health_pref is not None
        assert health_pref["threshold_value"] == 50.0

    def test_get_preferences_health_drop_returns_default_drop_threshold_15(
        self, client: TestClient, auth_headers: dict
    ):
        """When no pref record exists, drop_threshold defaults to 15."""
        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        prefs = response.json()["preferences"]
        health_pref = next(
            (p for p in prefs if p["alert_type"] == "customer_health_drop"), None
        )
        assert health_pref is not None
        assert health_pref["drop_threshold"] == 15

    def test_get_preferences_health_drop_enabled_by_default(
        self, client: TestClient, auth_headers: dict
    ):
        """When no pref record exists, is_enabled defaults to True."""
        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        prefs = response.json()["preferences"]
        health_pref = next(
            (p for p in prefs if p["alert_type"] == "customer_health_drop"), None
        )
        assert health_pref is not None
        assert health_pref["is_enabled"] is True

    def test_get_preferences_health_drop_default_channels(
        self, client: TestClient, auth_headers: dict
    ):
        """Default channels: channel_inapp=True, channel_slack=True, channel_email=False."""
        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        prefs = response.json()["preferences"]
        health_pref = next(
            (p for p in prefs if p["alert_type"] == "customer_health_drop"), None
        )
        assert health_pref is not None
        assert health_pref["channel_inapp"] is True
        assert health_pref["channel_slack"] is True
        assert health_pref["channel_email"] is False

    def test_get_preferences_health_drop_returns_saved_values(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """Returns saved threshold_value and drop_threshold when pref record exists."""
        pref = UserAlertPreference(
            user_id=test_user.id,
            alert_type="customer_health_drop",
            is_enabled=True,
            channel_inapp=True,
            channel_slack=False,
            channel_email=True,
            threshold_value=40.0,
            retention_days=30,
        )
        db.add(pref)
        db.commit()

        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)

        assert response.status_code == 200
        prefs = response.json()["preferences"]
        health_pref = next(
            (p for p in prefs if p["alert_type"] == "customer_health_drop"), None
        )
        assert health_pref is not None
        assert health_pref["threshold_value"] == 40.0
        assert health_pref["channel_email"] is True
        assert health_pref["channel_slack"] is False


# ---------------------------------------------------------------------------
# PUT /api/v1/notifications/preferences
# ---------------------------------------------------------------------------

class TestPutPreferencesHealthDrop:
    """PUT /api/v1/notifications/preferences accepts customer_health_drop with drop_threshold."""

    def test_put_preferences_creates_health_drop_pref(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """PUT creates a UserAlertPreference record for customer_health_drop."""
        response = client.put(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {
                        "alert_type": "customer_health_drop",
                        "is_enabled": True,
                        "channel_email": False,
                        "channel_slack": True,
                        "channel_inapp": True,
                        "threshold_value": 45.0,
                        "drop_threshold": 20,
                    }
                ]
            },
        )

        assert response.status_code == 200

        pref = db.query(UserAlertPreference).filter(
            UserAlertPreference.user_id == test_user.id,
            UserAlertPreference.alert_type == "customer_health_drop",
        ).first()
        assert pref is not None
        assert pref.threshold_value == 45.0

    def test_put_preferences_stores_and_returns_drop_threshold(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """PUT stores drop_threshold and GET returns it back."""
        client.put(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {
                        "alert_type": "customer_health_drop",
                        "is_enabled": True,
                        "channel_email": False,
                        "channel_slack": True,
                        "channel_inapp": True,
                        "threshold_value": 50.0,
                        "drop_threshold": 20,
                    }
                ]
            },
        )

        # Verify via GET
        response = client.get("/api/v1/notifications/preferences", headers=auth_headers)
        assert response.status_code == 200
        prefs = response.json()["preferences"]
        health_pref = next(
            (p for p in prefs if p["alert_type"] == "customer_health_drop"), None
        )
        assert health_pref is not None
        assert health_pref["drop_threshold"] == 20

    def test_put_preferences_updates_existing_health_drop_pref(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """PUT updates an existing customer_health_drop preference record."""
        # Create existing pref
        pref = UserAlertPreference(
            user_id=test_user.id,
            alert_type="customer_health_drop",
            is_enabled=True,
            channel_inapp=True,
            channel_slack=True,
            channel_email=False,
            threshold_value=50.0,
            retention_days=30,
        )
        db.add(pref)
        db.commit()

        # Update it
        response = client.put(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {
                        "alert_type": "customer_health_drop",
                        "is_enabled": False,
                        "channel_email": True,
                        "channel_slack": False,
                        "channel_inapp": True,
                        "threshold_value": 30.0,
                        "drop_threshold": 10,
                    }
                ]
            },
        )

        assert response.status_code == 200
        db.refresh(pref)
        assert pref.is_enabled is False
        assert pref.threshold_value == 30.0

    def test_put_preferences_drop_threshold_validation_min_5(
        self, client: TestClient, auth_headers: dict
    ):
        """drop_threshold must be >= 5; value < 5 returns 422."""
        response = client.put(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {
                        "alert_type": "customer_health_drop",
                        "is_enabled": True,
                        "channel_email": False,
                        "channel_slack": True,
                        "channel_inapp": True,
                        "threshold_value": 50.0,
                        "drop_threshold": 4,  # below minimum of 5
                    }
                ]
            },
        )

        assert response.status_code == 422

    def test_put_preferences_drop_threshold_validation_max_50(
        self, client: TestClient, auth_headers: dict
    ):
        """drop_threshold must be <= 50; value > 50 returns 422."""
        response = client.put(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {
                        "alert_type": "customer_health_drop",
                        "is_enabled": True,
                        "channel_email": False,
                        "channel_slack": True,
                        "channel_inapp": True,
                        "threshold_value": 50.0,
                        "drop_threshold": 51,  # above maximum of 50
                    }
                ]
            },
        )

        assert response.status_code == 422

    def test_put_preferences_threshold_value_validation_min_1(
        self, client: TestClient, auth_headers: dict
    ):
        """For customer_health_drop, threshold_value must be >= 1."""
        response = client.put(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {
                        "alert_type": "customer_health_drop",
                        "is_enabled": True,
                        "channel_email": False,
                        "channel_slack": True,
                        "channel_inapp": True,
                        "threshold_value": 0,  # below minimum of 1
                        "drop_threshold": 15,
                    }
                ]
            },
        )

        assert response.status_code == 422

    def test_put_preferences_threshold_value_validation_max_99(
        self, client: TestClient, auth_headers: dict
    ):
        """For customer_health_drop, threshold_value must be <= 99."""
        response = client.put(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {
                        "alert_type": "customer_health_drop",
                        "is_enabled": True,
                        "channel_email": False,
                        "channel_slack": True,
                        "channel_inapp": True,
                        "threshold_value": 100,  # above maximum of 99
                        "drop_threshold": 15,
                    }
                ]
            },
        )

        assert response.status_code == 422

    def test_put_preferences_drop_threshold_optional_defaults_to_15(
        self, client: TestClient, auth_headers: dict
    ):
        """drop_threshold is optional; when omitted, GET returns 15."""
        response = client.put(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {
                        "alert_type": "customer_health_drop",
                        "is_enabled": True,
                        "channel_email": False,
                        "channel_slack": True,
                        "channel_inapp": True,
                        "threshold_value": 50.0,
                        # no drop_threshold
                    }
                ]
            },
        )

        assert response.status_code == 200

        get_response = client.get("/api/v1/notifications/preferences", headers=auth_headers)
        prefs = get_response.json()["preferences"]
        health_pref = next(
            (p for p in prefs if p["alert_type"] == "customer_health_drop"), None
        )
        assert health_pref is not None
        assert health_pref["drop_threshold"] == 15  # default
