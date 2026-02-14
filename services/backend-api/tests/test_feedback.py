"""
Tests for feedback endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.user import User
from src.models.organization import Organization


class TestListFeedback:
    """Tests for GET /api/v1/feedback endpoint."""

    def test_list_feedback_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback_batch: list[FeedbackItem]
    ):
        """Test listing feedback items."""
        response = client.get(
            "/api/v1/feedback",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] == 5
        assert len(data["items"]) == 5

    def test_list_feedback_pagination(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback_batch: list[FeedbackItem]
    ):
        """Test feedback pagination."""
        response = client.get(
            "/api/v1/feedback?page=1&page_size=2",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_feedback_filter_sentiment(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback_batch: list[FeedbackItem]
    ):
        """Test filtering feedback by sentiment."""
        response = client.get(
            "/api/v1/feedback?sentiment=positive",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert all(item["sentiment_label"] == "positive" for item in data["items"])

    def test_list_feedback_filter_urgent(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback_batch: list[FeedbackItem]
    ):
        """Test filtering urgent feedback."""
        response = client.get(
            "/api/v1/feedback?is_urgent=true",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert all(item["is_urgent"] is True for item in data["items"])

    def test_list_feedback_unauthorized(self, client: TestClient):
        """Test listing feedback without authentication fails."""
        response = client.get("/api/v1/feedback")

        assert response.status_code in [401, 403]


class TestGetFeedback:
    """Tests for GET /api/v1/feedback/{feedback_id} endpoint."""

    def test_get_feedback_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback: FeedbackItem
    ):
        """Test getting single feedback item."""
        response = client.get(
            f"/api/v1/feedback/{test_feedback.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_feedback.id
        assert data["text"] == test_feedback.text
        assert data["sentiment_label"] == test_feedback.sentiment_label

    def test_get_feedback_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test getting non-existent feedback fails."""
        response = client.get(
            "/api/v1/feedback/99999",
            headers=auth_headers
        )

        assert response.status_code == 404

    def test_get_feedback_unauthorized(self, client: TestClient, test_feedback: FeedbackItem):
        """Test getting feedback without authentication fails."""
        response = client.get(f"/api/v1/feedback/{test_feedback.id}")

        assert response.status_code in [401, 403]


class TestCreateFeedback:
    """Tests for POST /api/v1/feedback endpoint."""

    def test_create_feedback_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session
    ):
        """Test creating new feedback."""
        response = client.post(
            "/api/v1/feedback",
            headers=auth_headers,
            json={
                "text": "This is a test feedback.",
                "source": "manual"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["text"] == "This is a test feedback."
        assert data["source"] == "manual"
        assert data["sentiment_label"] is None  # Not analyzed yet

        # Verify in database
        feedback = db.query(FeedbackItem).filter(FeedbackItem.id == data["id"]).first()
        assert feedback is not None
        assert feedback.text == "This is a test feedback."

    def test_create_feedback_missing_text(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test creating feedback without text fails."""
        response = client.post(
            "/api/v1/feedback",
            headers=auth_headers,
            json={
                "source": "manual"
                # Missing text
            }
        )

        assert response.status_code == 422  # Validation error

    def test_create_feedback_unauthorized(self, client: TestClient):
        """Test creating feedback without authentication fails."""
        response = client.post(
            "/api/v1/feedback",
            json={
                "text": "Test feedback",
                "source": "manual"
            }
        )

        assert response.status_code in [401, 403]


class TestUpdateFeedback:
    """Tests for PUT /api/v1/feedback/{feedback_id} endpoint."""

    def test_update_feedback_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback: FeedbackItem
    ):
        """Test updating feedback."""
        response = client.patch(
            f"/api/v1/feedback/{test_feedback.id}",
            headers=auth_headers,
            json={
                "text": "Updated feedback text",
                "source": "email"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Updated feedback text"
        assert data["id"] == test_feedback.id

    def test_update_feedback_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test updating non-existent feedback fails."""
        response = client.patch(
            "/api/v1/feedback/99999",
            headers=auth_headers,
            json={
                "text": "Updated text",
                "source": "email"
            }
        )

        assert response.status_code == 404

    def test_update_feedback_unauthorized(
        self,
        client: TestClient,
        test_feedback: FeedbackItem
    ):
        """Test updating feedback without authentication fails."""
        response = client.patch(
            f"/api/v1/feedback/{test_feedback.id}",
            json={
                "text": "Updated text",
                "source": "email"
            }
        )

        assert response.status_code in [401, 403]


class TestDeleteFeedback:
    """Tests for DELETE /api/v1/feedback/{feedback_id} endpoint."""

    def test_delete_feedback_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback: FeedbackItem,
        db: Session
    ):
        """Test deleting feedback."""
        response = client.delete(
            f"/api/v1/feedback/{test_feedback.id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify deleted from database
        feedback = db.query(FeedbackItem).filter(FeedbackItem.id == test_feedback.id).first()
        assert feedback is None

    def test_delete_feedback_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test deleting non-existent feedback fails."""
        response = client.delete(
            "/api/v1/feedback/99999",
            headers=auth_headers
        )

        assert response.status_code == 404

    def test_delete_feedback_unauthorized(
        self,
        client: TestClient,
        test_feedback: FeedbackItem
    ):
        """Test deleting feedback without authentication fails."""
        response = client.delete(f"/api/v1/feedback/{test_feedback.id}")

        assert response.status_code in [401, 403]


class TestAnalyzeFeedback:
    """Tests for POST /api/v1/analyze endpoint."""

    @pytest.mark.skip(reason="Requires analysis-engine dependencies (vaderSentiment) not installed in backend-api venv")
    def test_analyze_feedback_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization
    ):
        """Test analyzing feedback items."""
        # Create unanalyzed feedback
        feedback1 = FeedbackItem(
            organization_id=test_organization.id,
            text="This product is absolutely terrible!",
            source="email"
        )
        feedback2 = FeedbackItem(
            organization_id=test_organization.id,
            text="Love it! Best purchase ever.",
            source="survey"
        )
        db.add_all([feedback1, feedback2])
        db.commit()
        db.refresh(feedback1)
        db.refresh(feedback2)

        response = client.post(
            "/api/v1/analyze",
            headers=auth_headers,
            json={
                "feedback_ids": [feedback1.id, feedback2.id]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "Successfully analyzed" in data["message"]
        assert data["analyzed_count"] == 2

        # Verify feedback was analyzed
        db.refresh(feedback1)
        db.refresh(feedback2)

        assert feedback1.sentiment_label is not None
        assert feedback2.sentiment_label is not None

    def test_analyze_feedback_empty_list(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test analyzing empty list of feedback."""
        response = client.post(
            "/api/v1/analyze/",
            headers=auth_headers,
            json={
                "feedback_ids": []
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_analyze_feedback_unauthorized(self, client: TestClient):
        """Test analyzing feedback without authentication fails."""
        response = client.post(
            "/api/v1/analyze",
            json={
                "feedback_ids": [1, 2, 3]
            }
        )

        assert response.status_code in [401, 403]
