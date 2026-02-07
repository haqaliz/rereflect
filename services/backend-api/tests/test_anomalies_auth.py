"""
Tests for anomaly API authentication and organization isolation.
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
def org_a(db: Session) -> Organization:
    org = Organization(name="Org A", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def org_b(db: Session) -> Organization:
    org = Organization(name="Org B", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def user_a(db: Session, org_a: Organization) -> User:
    user = User(
        email="user_a@test.com",
        password_hash=hash_password("password123"),
        organization_id=org_a.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def user_b(db: Session, org_b: Organization) -> User:
    user = User(
        email="user_b@test.com",
        password_hash=hash_password("password123"),
        organization_id=org_b.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def headers_a(user_a: User) -> dict:
    token = create_access_token({
        "user_id": user_a.id,
        "organization_id": user_a.organization_id,
        "role": user_a.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def headers_b(user_b: User) -> dict:
    token = create_access_token({
        "user_id": user_b.id,
        "organization_id": user_b.organization_id,
        "role": user_b.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def anomaly_org_a(db: Session, org_a: Organization) -> SentimentAnomaly:
    anomaly = SentimentAnomaly(
        organization_id=org_a.id,
        detected_at=datetime.utcnow() - timedelta(hours=1),
        anomaly_type="negative_spike",
        severity="warning",
        baseline_negative_pct=10.0,
        current_negative_pct=35.0,
        deviation_pct=25.0,
        time_window_hours=24,
        feedback_count=20,
        is_resolved=False,
    )
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


@pytest.fixture
def anomaly_org_b(db: Session, org_b: Organization) -> SentimentAnomaly:
    anomaly = SentimentAnomaly(
        organization_id=org_b.id,
        detected_at=datetime.utcnow(),
        anomaly_type="negative_spike",
        severity="critical",
        baseline_negative_pct=15.0,
        current_negative_pct=60.0,
        deviation_pct=45.0,
        time_window_hours=24,
        feedback_count=30,
        is_resolved=False,
    )
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


class TestAnomalyAuth:
    """Tests for authentication on anomaly endpoints."""

    def test_list_requires_auth(self, client: TestClient):
        """Should return 403 without authentication."""
        response = client.get("/api/v1/anomalies/")
        assert response.status_code == 403

    def test_resolve_requires_auth(self, client: TestClient):
        """Should return 403 without authentication."""
        response = client.patch("/api/v1/anomalies/1/resolve")
        assert response.status_code == 403


class TestAnomalyOrgIsolation:
    """Tests for organization-level data isolation."""

    def test_user_a_only_sees_org_a_anomalies(
        self, client: TestClient, headers_a: dict,
        anomaly_org_a: SentimentAnomaly, anomaly_org_b: SentimentAnomaly,
    ):
        """User A should only see anomalies from Org A."""
        response = client.get("/api/v1/anomalies/", headers=headers_a)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == anomaly_org_a.id

    def test_user_b_only_sees_org_b_anomalies(
        self, client: TestClient, headers_b: dict,
        anomaly_org_a: SentimentAnomaly, anomaly_org_b: SentimentAnomaly,
    ):
        """User B should only see anomalies from Org B."""
        response = client.get("/api/v1/anomalies/", headers=headers_b)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == anomaly_org_b.id

    def test_cannot_resolve_other_orgs_anomaly(
        self, client: TestClient, headers_a: dict,
        anomaly_org_b: SentimentAnomaly,
    ):
        """User A should not be able to resolve Org B's anomaly (returns 404)."""
        response = client.patch(
            f"/api/v1/anomalies/{anomaly_org_b.id}/resolve",
            headers=headers_a,
        )
        assert response.status_code == 404

    def test_can_resolve_own_orgs_anomaly(
        self, client: TestClient, headers_a: dict,
        anomaly_org_a: SentimentAnomaly,
    ):
        """User A should be able to resolve Org A's anomaly."""
        response = client.patch(
            f"/api/v1/anomalies/{anomaly_org_a.id}/resolve",
            headers=headers_a,
        )
        assert response.status_code == 200
        assert response.json()["is_resolved"] is True


class TestAnomalyLimitParam:
    """Tests for limit query parameter."""

    def test_limit_restricts_results(
        self, client: TestClient, headers_a: dict, db: Session, org_a: Organization,
    ):
        """Should respect the limit parameter."""
        # Create 5 anomalies
        for i in range(5):
            db.add(SentimentAnomaly(
                organization_id=org_a.id,
                detected_at=datetime.utcnow() - timedelta(hours=i),
                anomaly_type="negative_spike",
                severity="warning",
                baseline_negative_pct=10.0,
                current_negative_pct=30.0 + i,
                deviation_pct=20.0 + i,
                time_window_hours=24,
                feedback_count=10,
                is_resolved=False,
            ))
        db.commit()

        response = client.get("/api/v1/anomalies/?limit=3", headers=headers_a)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5  # Total count is all matching
        assert len(data["items"]) == 3  # But only 3 returned
