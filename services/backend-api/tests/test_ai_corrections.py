"""
TDD tests for AI Human-in-the-Loop corrections (Track B).

Covers:
  1. test_submit_thumbs_up
  2. test_submit_thumbs_down_with_text
  3. test_submit_category_correction
  4. test_stats_returns_counts
  5. test_list_corrections_paginated
  6. test_list_requires_admin
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.ai_correction import AICorrection
from src.models.feedback import FeedbackItem
from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


# ── Helpers ───────────────────────────────────────────────────────────────────

def _member_token(db: Session, org: Organization) -> str:
    """Create a member-role user and return their JWT token."""
    user = User(
        email="member@example.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return create_access_token({
        "user_id": user.id,
        "organization_id": org.id,
        "role": "member",
    })


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSubmitCorrection:
    """POST /api/v1/ai-corrections"""

    def test_submit_thumbs_up(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Thumbs-up on a copilot message is saved with signal=thumbs_up."""
        payload = {
            "correction_type": "copilot_response",
            "entity_type": "conversation_message",
            "entity_id": 42,
            "signal": "thumbs_up",
            "original_value": "Here is your summary...",
        }
        response = client.post("/api/v1/ai-corrections", json=payload, headers=auth_headers)
        assert response.status_code == 201

        data = response.json()
        assert data["signal"] == "thumbs_up"
        assert data["correction_type"] == "copilot_response"
        assert data["corrected_value"] is None
        assert data["feedback_text"] is None

        # Persisted in DB
        row = db.query(AICorrection).filter(AICorrection.id == data["id"]).first()
        assert row is not None
        assert row.signal == "thumbs_up"

    def test_submit_thumbs_down_with_text(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
    ):
        """Thumbs-down with optional feedback text is stored correctly."""
        payload = {
            "correction_type": "copilot_response",
            "entity_type": "conversation_message",
            "entity_id": 7,
            "signal": "thumbs_down",
            "original_value": "I cannot answer that.",
            "feedback_text": "The answer was actually available in the data.",
        }
        response = client.post("/api/v1/ai-corrections", json=payload, headers=auth_headers)
        assert response.status_code == 201

        data = response.json()
        assert data["signal"] == "thumbs_down"
        assert data["feedback_text"] == "The answer was actually available in the data."

    def test_submit_category_correction(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
    ):
        """Category correction carries original_value and corrected_value."""
        payload = {
            "correction_type": "sentiment",
            "entity_type": "feedback_item",
            "entity_id": 99,
            "signal": "correction",
            "original_value": "negative",
            "corrected_value": "neutral",
        }
        response = client.post("/api/v1/ai-corrections", json=payload, headers=auth_headers)
        assert response.status_code == 201

        data = response.json()
        assert data["original_value"] == "negative"
        assert data["corrected_value"] == "neutral"
        assert data["signal"] == "correction"

    def test_submit_requires_auth(self, client: TestClient):
        """Unauthenticated request is rejected with 403."""
        response = client.post("/api/v1/ai-corrections", json={
            "correction_type": "sentiment",
            "entity_type": "feedback_item",
            "entity_id": 1,
            "signal": "thumbs_up",
            "original_value": "negative",
        })
        assert response.status_code == 403


class TestCategoryCorrectionCharacterization:
    """POST /api/v1/ai-corrections — category correction baseline.

    Locks current behavior before the create_ai_correction helper extraction:
    a category correction is persisted with user_id=current_user.id and does
    NOT mutate the target feedback's pain_point_category.
    """

    def test_category_correction_persists_and_does_not_mutate_feedback(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="The billing page keeps timing out.",
            source="email",
            sentiment_label="negative",
            sentiment_score=-0.6,
            pain_point_category="performance",
            is_urgent=False,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        payload = {
            "correction_type": "category",
            "entity_type": "feedback_item",
            "entity_id": feedback.id,
            "signal": "correction",
            "original_value": "performance",
            "corrected_value": "billing",
        }
        response = client.post(
            "/api/v1/ai-corrections", json=payload, headers=auth_headers
        )
        assert response.status_code == 201

        data = response.json()
        assert data["correction_type"] == "category"
        assert data["entity_type"] == "feedback_item"
        assert data["entity_id"] == feedback.id
        assert data["signal"] == "correction"
        assert data["original_value"] == "performance"
        assert data["corrected_value"] == "billing"

        # Persisted with user_id = current_user.id
        row = db.query(AICorrection).filter(AICorrection.id == data["id"]).first()
        assert row is not None
        assert row.user_id == test_user.id
        assert row.organization_id == test_organization.id

        # Feedback's own category is NOT changed by submitting a correction
        db.refresh(feedback)
        assert feedback.pain_point_category == "performance"


class TestCorrectionStats:
    """GET /api/v1/ai-corrections/stats"""

    def _seed_corrections(self, db: Session, org_id: int, user_id: int):
        corrections = [
            AICorrection(
                organization_id=org_id,
                user_id=user_id,
                correction_type="sentiment",
                entity_type="feedback_item",
                entity_id=1,
                signal="correction",
                original_value="negative",
                corrected_value="neutral",
            ),
            AICorrection(
                organization_id=org_id,
                user_id=user_id,
                correction_type="sentiment",
                entity_type="feedback_item",
                entity_id=2,
                signal="correction",
                original_value="negative",
                corrected_value="positive",
            ),
            AICorrection(
                organization_id=org_id,
                user_id=user_id,
                correction_type="copilot_response",
                entity_type="conversation_message",
                entity_id=10,
                signal="thumbs_down",
                original_value="Some AI reply",
            ),
        ]
        for c in corrections:
            db.add(c)
        db.commit()

    def test_stats_returns_counts(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        """Stats endpoint returns total, this_month, by_type, and most_corrected."""
        self._seed_corrections(db, test_organization.id, test_user.id)

        response = client.get("/api/v1/ai-corrections/stats", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 3
        assert data["this_month"] == 3  # all seeded now
        assert "by_type" in data
        assert data["by_type"]["sentiment"] == 2
        assert data["by_type"]["copilot_response"] == 1
        assert "most_corrected" in data
        assert isinstance(data["most_corrected"], list)

    def test_stats_requires_auth(self, client: TestClient):
        """Unauthenticated request is rejected."""
        response = client.get("/api/v1/ai-corrections/stats")
        assert response.status_code == 403


class TestListCorrections:
    """GET /api/v1/ai-corrections"""

    def _seed(self, db: Session, org_id: int, user_id: int, count: int = 5):
        for i in range(count):
            db.add(AICorrection(
                organization_id=org_id,
                user_id=user_id,
                correction_type="sentiment",
                entity_type="feedback_item",
                entity_id=i + 1,
                signal="correction",
                original_value="negative",
                corrected_value="neutral",
            ))
        db.commit()

    def test_list_corrections_paginated(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        """Admin can list corrections with pagination (page/page_size)."""
        self._seed(db, test_organization.id, test_user.id, count=5)

        response = client.get(
            "/api/v1/ai-corrections?page=1&page_size=3",
            headers=auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) == 3
        assert data["total"] == 5

    def test_list_corrections_second_page(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        """Second page returns remaining items."""
        self._seed(db, test_organization.id, test_user.id, count=5)

        response = client.get(
            "/api/v1/ai-corrections?page=2&page_size=3",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

    def test_list_requires_admin(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
    ):
        """Member-role user is forbidden from listing corrections."""
        token = _member_token(db, test_organization)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/ai-corrections", headers=headers)
        assert response.status_code == 403

    def test_list_requires_auth(self, client: TestClient):
        """Unauthenticated request is rejected."""
        response = client.get("/api/v1/ai-corrections")
        assert response.status_code == 403
