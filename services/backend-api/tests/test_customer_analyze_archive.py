"""
TDD tests for:
- POST /api/v1/customers/{email}/analyze — on-demand LLM analysis (202 Accepted)
- Archive trigger: feedback delete → is_archived=True when 0 remaining
- Unarchive: already tested in test_health_score_service.py
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Analyze Test Company", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_org: Organization) -> User:
    user = User(
        email="analyzeuser@example.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_headers(pro_user: User) -> dict:
    token = create_access_token({
        "user_id": pro_user.id,
        "organization_id": pro_user.organization_id,
        "role": pro_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Analyze Company", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_org: Organization) -> User:
    user = User(
        email="freeanalyze@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_headers(free_user: User) -> dict:
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def make_health(db, org, email, **kwargs) -> CustomerHealth:
    defaults = dict(
        health_score=60,
        risk_level="moderate",
        feedback_count=5,
        confidence_level="medium",
        churn_risk_component=50,
        sentiment_component=60,
        resolution_component=70,
        frequency_component=55,
        last_feedback_at=datetime.utcnow(),
        is_archived=False,
    )
    defaults.update(kwargs)
    h = CustomerHealth(organization_id=org.id, customer_email=email, **defaults)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def make_feedback(db, org, email, text="test") -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org.id,
        customer_email=email,
        text=text,
        source="email",
        workflow_status="new",
        is_urgent=False,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------------------------------------------------------------------------
# On-Demand Analysis Endpoint: POST /api/v1/customers/{email}/analyze
# ---------------------------------------------------------------------------

class TestCustomerAnalyze:

    def test_analyze_returns_202(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        """POST analyze should return 202 Accepted."""
        make_health(db, pro_org, "analyze@acme.com")
        with patch("src.background.queue_analyze_feedback") as mock_queue:
            mock_queue.return_value = "task-123"
            with patch("src.background.get_celery_app"):
                # Mock the Celery send_task call
                with patch("src.api.routes.customers._queue_llm_analysis") as mock_llm:
                    mock_llm.return_value = "task-abc"
                    response = client.post("/api/v1/customers/analyze@acme.com/analyze", headers=pro_headers)
        assert response.status_code == 202

    def test_analyze_response_has_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        """Response should have message and estimated_wait_seconds."""
        make_health(db, pro_org, "analyze2@acme.com")
        with patch("src.api.routes.customers._queue_llm_analysis") as mock_llm:
            mock_llm.return_value = "task-abc"
            response = client.post("/api/v1/customers/analyze2@acme.com/analyze", headers=pro_headers)
        assert response.status_code == 202
        data = response.json()
        assert "message" in data
        assert "estimated_wait_seconds" in data

    def test_analyze_404_when_no_health_record(self, client: TestClient, pro_org: Organization, pro_headers: dict):
        """Should return 404 if customer has no health record."""
        with patch("src.api.routes.customers._queue_llm_analysis") as mock_llm:
            mock_llm.return_value = "task-abc"
            response = client.post("/api/v1/customers/nobody@acme.com/analyze", headers=pro_headers)
        assert response.status_code == 404

    def test_analyze_requires_churn_llm_insights_feature(self, client: TestClient, free_headers: dict):
        """Free plan users should get 403."""
        response = client.post("/api/v1/customers/anyone@example.com/analyze", headers=free_headers)
        assert response.status_code == 403

    def test_analyze_queues_task(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        """Should call the task queue function."""
        make_health(db, pro_org, "queued@acme.com")
        with patch("src.api.routes.customers._queue_llm_analysis") as mock_llm:
            mock_llm.return_value = "task-xyz"
            response = client.post("/api/v1/customers/queued@acme.com/analyze", headers=pro_headers)
        assert response.status_code == 202
        mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# Archive Trigger Tests
# ---------------------------------------------------------------------------

class TestFeedbackDeleteArchiveTrigger:
    """After feedback deletion, if remaining count is 0, customer should be archived."""

    def test_delete_last_feedback_archives_customer(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        """Deleting the last feedback for a customer should set is_archived=True."""
        # Create customer health record
        health = make_health(db, pro_org, "lastfb@acme.com", feedback_count=1)

        # Create a single feedback
        fb = make_feedback(db, pro_org, "lastfb@acme.com", text="Only feedback")

        # Delete the feedback
        response = client.delete(f"/api/v1/feedback/{fb.id}", headers=pro_headers)
        assert response.status_code == 204

        # CustomerHealth should now be archived
        db.refresh(health)
        assert health.is_archived == True

    def test_delete_non_last_feedback_does_not_archive(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        """Deleting feedback when others remain should NOT archive the customer."""
        health = make_health(db, pro_org, "multifb@acme.com", feedback_count=2)

        fb1 = make_feedback(db, pro_org, "multifb@acme.com", text="First feedback")
        fb2 = make_feedback(db, pro_org, "multifb@acme.com", text="Second feedback")

        # Delete only one feedback
        response = client.delete(f"/api/v1/feedback/{fb1.id}", headers=pro_headers)
        assert response.status_code == 204

        # CustomerHealth should NOT be archived (still has fb2)
        db.refresh(health)
        assert health.is_archived == False

    def test_delete_feedback_for_customer_without_health_record_is_safe(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        """Deleting feedback for a customer with no health record should not raise errors."""
        fb = make_feedback(db, pro_org, "nohealthrecord@acme.com", text="Some feedback")

        response = client.delete(f"/api/v1/feedback/{fb.id}", headers=pro_headers)
        # Should succeed (no 500)
        assert response.status_code == 204

    def test_delete_feedback_without_customer_email_is_safe(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        """Deleting feedback with no customer_email should not raise errors."""
        fb = FeedbackItem(
            organization_id=pro_org.id,
            text="No customer email feedback",
            source="manual",
            is_urgent=False,
        )
        db.add(fb)
        db.commit()
        db.refresh(fb)

        response = client.delete(f"/api/v1/feedback/{fb.id}", headers=pro_headers)
        assert response.status_code == 204
