"""
Tests for anomaly detection API: listing, resolving, and alert preferences.
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.anomaly import SentimentAnomaly
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner@anomalytest.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict:
    token = create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_anomalies(db: Session, test_organization: Organization):
    """Create sample anomalies for testing."""
    anomalies = [
        SentimentAnomaly(
            organization_id=test_organization.id,
            detected_at=datetime.utcnow() - timedelta(hours=2),
            anomaly_type="negative_spike",
            severity="critical",
            baseline_negative_pct=15.0,
            current_negative_pct=55.0,
            deviation_pct=40.0,
            time_window_hours=24,
            feedback_count=50,
            is_resolved=False,
        ),
        SentimentAnomaly(
            organization_id=test_organization.id,
            detected_at=datetime.utcnow() - timedelta(hours=26),
            anomaly_type="negative_spike",
            severity="warning",
            baseline_negative_pct=20.0,
            current_negative_pct=38.0,
            deviation_pct=18.0,
            time_window_hours=24,
            feedback_count=30,
            is_resolved=True,
            resolved_at=datetime.utcnow() - timedelta(hours=24),
        ),
        SentimentAnomaly(
            organization_id=test_organization.id,
            detected_at=datetime.utcnow() - timedelta(hours=1),
            anomaly_type="negative_spike",
            severity="warning",
            baseline_negative_pct=18.0,
            current_negative_pct=35.0,
            deviation_pct=17.0,
            time_window_hours=24,
            feedback_count=25,
            is_resolved=False,
        ),
    ]
    for a in anomalies:
        db.add(a)
    db.commit()
    for a in anomalies:
        db.refresh(a)
    return anomalies


class TestAnomalyList:
    """Tests for GET /api/v1/anomalies/."""

    def test_list_all_anomalies(
        self, client: TestClient, owner_headers: dict, sample_anomalies
    ):
        response = client.get("/api/v1/anomalies/", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_list_unresolved_anomalies(
        self, client: TestClient, owner_headers: dict, sample_anomalies
    ):
        response = client.get(
            "/api/v1/anomalies/?is_resolved=false", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["is_resolved"] is False

    def test_list_resolved_anomalies(
        self, client: TestClient, owner_headers: dict, sample_anomalies
    ):
        response = client.get(
            "/api/v1/anomalies/?is_resolved=true", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["is_resolved"] is True

    def test_filter_by_severity(
        self, client: TestClient, owner_headers: dict, sample_anomalies
    ):
        response = client.get(
            "/api/v1/anomalies/?severity=critical", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["severity"] == "critical"

    def test_anomaly_response_fields(
        self, client: TestClient, owner_headers: dict, sample_anomalies
    ):
        response = client.get("/api/v1/anomalies/", headers=owner_headers)
        data = response.json()
        item = data["items"][0]
        assert "id" in item
        assert "anomaly_type" in item
        assert "severity" in item
        assert "baseline_negative_pct" in item
        assert "current_negative_pct" in item
        assert "deviation_pct" in item
        assert "time_window_hours" in item
        assert "feedback_count" in item
        assert "is_resolved" in item
        assert "detected_at" in item

    def test_empty_anomalies(
        self, client: TestClient, owner_headers: dict
    ):
        response = client.get("/api/v1/anomalies/", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_anomalies_ordered_by_detected_at_desc(
        self, client: TestClient, owner_headers: dict, sample_anomalies
    ):
        response = client.get("/api/v1/anomalies/", headers=owner_headers)
        data = response.json()
        dates = [item["detected_at"] for item in data["items"]]
        assert dates == sorted(dates, reverse=True)


class TestAnomalyResolve:
    """Tests for PATCH /api/v1/anomalies/{id}/resolve."""

    def test_resolve_anomaly(
        self, client: TestClient, owner_headers: dict, sample_anomalies
    ):
        unresolved = sample_anomalies[0]
        response = client.patch(
            f"/api/v1/anomalies/{unresolved.id}/resolve",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_resolved"] is True
        assert data["resolved_at"] is not None

    def test_resolve_already_resolved(
        self, client: TestClient, owner_headers: dict, sample_anomalies
    ):
        resolved = sample_anomalies[1]
        response = client.patch(
            f"/api/v1/anomalies/{resolved.id}/resolve",
            headers=owner_headers,
        )
        assert response.status_code == 400

    def test_resolve_nonexistent(
        self, client: TestClient, owner_headers: dict
    ):
        response = client.patch(
            "/api/v1/anomalies/99999/resolve",
            headers=owner_headers,
        )
        assert response.status_code == 404


class TestAlertPreferences:
    """Tests for alert channel preferences on /api/v1/auth/me/preferences."""

    def test_get_preferences_includes_alert_channels(
        self, client: TestClient, owner_headers: dict
    ):
        response = client.get("/api/v1/auth/me/preferences", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert "alert_channels" in data

    def test_update_alert_channels(
        self, client: TestClient, owner_headers: dict
    ):
        response = client.patch(
            "/api/v1/auth/me/preferences",
            headers=owner_headers,
            json={"alert_channels": {"dashboard": True, "email": True, "slack": False}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["alert_channels"]["dashboard"] is True
        assert data["alert_channels"]["email"] is True
        assert data["alert_channels"]["slack"] is False

    def test_alert_channels_persist(
        self, client: TestClient, owner_headers: dict
    ):
        # Set alert channels
        client.patch(
            "/api/v1/auth/me/preferences",
            headers=owner_headers,
            json={"alert_channels": {"dashboard": False, "email": True, "slack": True}},
        )
        # Read back
        response = client.get("/api/v1/auth/me/preferences", headers=owner_headers)
        data = response.json()
        assert data["alert_channels"]["dashboard"] is False
        assert data["alert_channels"]["email"] is True
        assert data["alert_channels"]["slack"] is True
