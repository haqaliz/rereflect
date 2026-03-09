"""
Tests for AI response generation endpoint.

TDD order:
1. GET /feedback/{id}/responses — list responses (empty then with records)
2. POST /feedback/{id}/responses/generate — AI generation
   a. 404 for missing feedback
   b. Successful generation (mock LLM)
   c. Limit enforcement (402 when over quota)
   d. 503 on LLM failure
3. POST /feedback/{id}/responses/send — save / send
   a. clipboard saves with status=copied
   b. Unknown feedback returns 404
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.feedback_response import FeedbackResponse
from src.models.organization import Organization
from src.models.user import User


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def feedback_item(db: Session, test_organization: Organization) -> FeedbackItem:
    """A feedback item owned by the test org."""
    item = FeedbackItem(
        organization_id=test_organization.id,
        text="The export button fails every time I click it.",
        source="email",
        sentiment_label="negative",
        is_urgent=False,
        pain_point_category="Bug Report",
        churn_risk_score=30,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# ============================================================================
# List responses
# ============================================================================

class TestListFeedbackResponses:
    def test_list_returns_empty_when_no_responses(
        self, client: TestClient, auth_headers: dict, feedback_item: FeedbackItem
    ):
        response = client.get(
            f"/api/v1/feedback/{feedback_item.id}/responses",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_returns_recorded_responses(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        feedback_item: FeedbackItem,
        test_user: User,
    ):
        """After saving a response, it appears in the list."""
        fr = FeedbackResponse(
            feedback_id=feedback_item.id,
            organization_id=test_organization.id,
            user_id=test_user.id,
            response_text="Hi, thank you for the report!",
            channel="clipboard",
            source="manual",
            status="copied",
        )
        db.add(fr)
        db.commit()

        response = client.get(
            f"/api/v1/feedback/{feedback_item.id}/responses",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["channel"] == "clipboard"
        assert data[0]["source"] == "manual"
        assert data[0]["status"] == "copied"

    def test_list_includes_user_name(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        feedback_item: FeedbackItem,
        test_user: User,
    ):
        fr = FeedbackResponse(
            feedback_id=feedback_item.id,
            organization_id=test_organization.id,
            user_id=test_user.id,
            response_text="Hello!",
            channel="clipboard",
            source="manual",
            status="copied",
        )
        db.add(fr)
        db.commit()

        response = client.get(
            f"/api/v1/feedback/{feedback_item.id}/responses",
            headers=auth_headers,
        )
        data = response.json()
        # user_name is derived from email (test@example.com → "test")
        assert data[0]["user_name"] is not None

    def test_list_returns_404_for_other_org_feedback(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
    ):
        other_org = Organization(name="Other", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        other_feedback = FeedbackItem(
            organization_id=other_org.id,
            text="Some text",
            source="email",
            sentiment_label="neutral",
        )
        db.add(other_feedback)
        db.commit()
        db.refresh(other_feedback)

        response = client.get(
            f"/api/v1/feedback/{other_feedback.id}/responses",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_list_requires_auth(self, client: TestClient, feedback_item: FeedbackItem):
        response = client.get(f"/api/v1/feedback/{feedback_item.id}/responses")
        assert response.status_code in (401, 403)


# ============================================================================
# AI generation
# ============================================================================

class TestGenerateAIResponse:
    def test_generate_returns_404_for_missing_feedback(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.post(
            "/api/v1/feedback/99999/responses/generate",
            json={"tone": "professional"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_generate_calls_llm_and_returns_text(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
        test_organization: Organization,
        db: Session,
    ):
        """Should call the LLM and return generated text plus usage counts."""
        mock_result = {
            "response_text": "Hi, thank you for reporting this bug. We are on it!",
            "tokens_used": 120,
        }

        with patch(
            "src.api.routes.feedback_responses.generate_response",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                f"/api/v1/feedback/{feedback_item.id}/responses/generate",
                json={"tone": "professional"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["response_text"] == mock_result["response_text"]
        assert data["tokens_used"] == 120
        assert "remaining_this_month" in data

    def test_generate_increments_usage_counter(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
        test_organization: Organization,
        db: Session,
    ):
        """Usage counter on org should be incremented after a successful generation."""
        initial_count = test_organization.ai_responses_generated or 0

        mock_result = {"response_text": "Response text", "tokens_used": 100}
        with patch(
            "src.api.routes.feedback_responses.generate_response",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            client.post(
                f"/api/v1/feedback/{feedback_item.id}/responses/generate",
                json={},
                headers=auth_headers,
            )

        db.refresh(test_organization)
        assert test_organization.ai_responses_generated == initial_count + 1

    def test_generate_enforces_monthly_limit(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
        test_organization: Organization,
        db: Session,
    ):
        """When monthly limit is reached, should return 402."""
        # Pro plan limit is 50; set counter to 50
        test_organization.ai_responses_generated = 50
        db.commit()

        response = client.post(
            f"/api/v1/feedback/{feedback_item.id}/responses/generate",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 402
        data = response.json()
        assert data["detail"]["error"] == "ai_response_limit_exceeded"

    def test_generate_returns_503_on_llm_failure(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
    ):
        """LLM failure should return 503."""
        with patch(
            "src.api.routes.feedback_responses.generate_response",
            new_callable=AsyncMock,
            side_effect=RuntimeError("OPENAI_API_KEY not configured"),
        ):
            response = client.post(
                f"/api/v1/feedback/{feedback_item.id}/responses/generate",
                json={},
                headers=auth_headers,
            )
        assert response.status_code == 503

    def test_generate_uses_tone_override(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
    ):
        """Tone from the request is passed to generate_response."""
        captured: dict = {}

        async def mock_gen(feedback, org, user, tone=None):
            captured["tone"] = tone
            return {"response_text": "Response", "tokens_used": 50}

        with patch("src.api.routes.feedback_responses.generate_response", new=mock_gen):
            client.post(
                f"/api/v1/feedback/{feedback_item.id}/responses/generate",
                json={"tone": "empathetic"},
                headers=auth_headers,
            )

        assert captured.get("tone") == "empathetic"

    def test_generate_returns_remaining_this_month(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
        test_organization: Organization,
        db: Session,
    ):
        """remaining_this_month decreases correctly after generation."""
        test_organization.ai_responses_generated = 10  # used 10, limit 50 → 39 after generation
        db.commit()

        mock_result = {"response_text": "Text", "tokens_used": 80}
        with patch(
            "src.api.routes.feedback_responses.generate_response",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                f"/api/v1/feedback/{feedback_item.id}/responses/generate",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 200
        # After incrementing: used=11, limit=50, remaining=39
        assert response.json()["remaining_this_month"] == 39
