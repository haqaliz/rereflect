"""
TDD tests for event emissions from route handlers.

RED phase: These tests are written BEFORE the implementation.
They verify that emit_event() is called with the correct arguments
after DB mutations in feedback, workflow, and notification routes.
"""

import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.user import User
from src.models.organization import Organization
from src.models.notification import Notification
from src.models.usage import UsageRecord
from src.api.auth import hash_password, create_access_token


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_usage(db: Session, org_id: int) -> UsageRecord:
    """Create a usage record for the org if it doesn't exist."""
    from datetime import datetime, timedelta
    usage = db.query(UsageRecord).filter(UsageRecord.organization_id == org_id).first()
    if not usage:
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        usage = UsageRecord(
            organization_id=org_id,
            period_start=period_start,
            period_end=period_start + timedelta(days=30),
            feedback_count=0,
            overage_feedback=0,
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)
    return usage


def _make_feedback(db: Session, org_id: int, **kwargs) -> FeedbackItem:
    defaults = dict(text="Test feedback", source="manual", is_urgent=False)
    defaults.update(kwargs)
    fb = FeedbackItem(organization_id=org_id, **defaults)
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _make_notification(db: Session, user_id: int, org_id: int) -> Notification:
    from datetime import datetime, timedelta
    n = Notification(
        user_id=user_id,
        organization_id=org_id,
        type="urgent_feedback",
        title="Test notification",
        message="Test body",
        is_read=False,
        is_dismissed=False,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


# ── Feedback Event Tests ───────────────────────────────────────────────────────

class TestFeedbackEventEmissions:

    def test_create_feedback_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_user: User,
        db: Session,
    ):
        """POST /feedback/ → emit_event called with 'feedback:created'."""
        _make_usage(db, test_organization.id)

        with patch("src.api.routes.feedback.emit_event", new_callable=AsyncMock) as mock_emit:
            with patch("src.background.queue_analyze_feedback", return_value=None):
                response = client.post(
                    "/api/v1/feedback/",
                    json={"text": "New feedback text", "source": "manual"},
                    headers=auth_headers,
                )

        assert response.status_code == 201
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "feedback:created"
        assert "id" in kwargs["data"]
        assert kwargs["org_id"] == test_organization.id

    def test_create_feedback_emits_event_with_title_and_source(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_user: User,
        db: Session,
    ):
        """feedback:created event data includes id and source."""
        _make_usage(db, test_organization.id)

        with patch("src.api.routes.feedback.emit_event", new_callable=AsyncMock) as mock_emit:
            with patch("src.background.queue_analyze_feedback", return_value=None):
                response = client.post(
                    "/api/v1/feedback/",
                    json={"text": "Feedback with source", "source": "email"},
                    headers=auth_headers,
                )

        assert response.status_code == 201
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["data"]["source"] == "email"

    def test_update_feedback_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_feedback: FeedbackItem,
        db: Session,
    ):
        """PATCH /feedback/:id → emit_event called with 'feedback:updated'."""
        with patch("src.api.routes.feedback.emit_event", new_callable=AsyncMock) as mock_emit:
            response = client.patch(
                f"/api/v1/feedback/{test_feedback.id}",
                json={"text": "Updated text", "source": "manual"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "feedback:updated"
        assert kwargs["data"]["id"] == test_feedback.id
        assert kwargs["org_id"] == test_organization.id

    def test_delete_feedback_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_feedback: FeedbackItem,
        db: Session,
    ):
        """DELETE /feedback/:id → emit_event called with 'feedback:deleted'."""
        feedback_id = test_feedback.id

        with patch("src.api.routes.feedback.emit_event", new_callable=AsyncMock) as mock_emit:
            response = client.delete(
                f"/api/v1/feedback/{feedback_id}",
                headers=auth_headers,
            )

        assert response.status_code == 204
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "feedback:deleted"
        assert kwargs["data"]["id"] == feedback_id
        assert kwargs["org_id"] == test_organization.id

    def test_import_csv_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        db: Session,
    ):
        """POST /feedback/import-csv → emit_event called with 'feedback:imported'."""
        _make_usage(db, test_organization.id)

        csv_content = "text,source\nFirst feedback,email\nSecond feedback,manual\n"
        csv_file = io.BytesIO(csv_content.encode("utf-8"))

        with patch("src.api.routes.feedback.emit_event", new_callable=AsyncMock) as mock_emit:
            with patch("src.background.queue_analyze_batch", return_value=None):
                response = client.post(
                    "/api/v1/feedback/import-csv",
                    files={"file": ("test.csv", csv_file, "text/csv")},
                    headers=auth_headers,
                )

        assert response.status_code == 200
        data = response.json()
        assert data["imported_count"] > 0

        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "feedback:imported"
        assert "count" in kwargs["data"]
        assert kwargs["data"]["count"] == data["imported_count"]
        assert kwargs["org_id"] == test_organization.id

    def test_feedback_event_broadcasts_to_all(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_user: User,
        test_feedback: FeedbackItem,
        db: Session,
    ):
        """emit_event is called without exclude_user_id so all tabs receive the event."""
        with patch("src.api.routes.feedback.emit_event", new_callable=AsyncMock) as mock_emit:
            response = client.patch(
                f"/api/v1/feedback/{test_feedback.id}",
                json={"text": "Broadcast test", "source": "manual"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert "exclude_user_id" not in kwargs


# ── Workflow Event Tests ──────────────────────────────────────────────────────

class TestWorkflowEventEmissions:

    def test_change_status_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_user: User,
        test_feedback: FeedbackItem,
        db: Session,
    ):
        """POST /workflow/status → emit_event called with 'workflow:status_changed'."""
        with patch("src.api.routes.workflow.emit_event", new_callable=AsyncMock) as mock_emit:
            response = client.post(
                "/api/v1/workflow/status",
                json={"feedback_ids": [test_feedback.id], "new_status": "in_review"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "workflow:status_changed"
        assert kwargs["data"]["feedback_ids"] == [test_feedback.id]
        assert kwargs["data"]["new_status"] == "in_review"
        assert kwargs["org_id"] == test_organization.id
        assert "exclude_user_id" not in kwargs

    def test_assign_feedback_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_user: User,
        test_feedback: FeedbackItem,
        db: Session,
    ):
        """POST /workflow/assign → emit_event called with 'workflow:assigned'."""
        with patch("src.api.routes.workflow.emit_event", new_callable=AsyncMock) as mock_emit:
            response = client.post(
                "/api/v1/workflow/assign",
                json={"feedback_ids": [test_feedback.id], "assign_to_user_id": test_user.id},
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "workflow:assigned"
        assert kwargs["data"]["feedback_ids"] == [test_feedback.id]
        assert kwargs["data"]["assignee_id"] == test_user.id
        assert kwargs["org_id"] == test_organization.id
        assert "exclude_user_id" not in kwargs

    def test_create_note_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_user: User,
        test_feedback: FeedbackItem,
        db: Session,
    ):
        """POST /workflow/:id/notes → emit_event called with 'workflow:note_added'."""
        with patch("src.api.routes.workflow.emit_event", new_callable=AsyncMock) as mock_emit:
            response = client.post(
                f"/api/v1/workflow/{test_feedback.id}/notes",
                json={"content": "This is a test note."},
                headers=auth_headers,
            )

        assert response.status_code == 201
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "workflow:note_added"
        assert kwargs["data"]["feedback_id"] == test_feedback.id
        assert "note_id" in kwargs["data"]
        assert kwargs["org_id"] == test_organization.id
        assert "exclude_user_id" not in kwargs


# ── Notification Event Tests ──────────────────────────────────────────────────

class TestNotificationEventEmissions:

    def test_mark_read_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_user: User,
        db: Session,
    ):
        """PATCH /notifications/:id/read → emit_event called with 'notification:read'."""
        notification = _make_notification(db, test_user.id, test_organization.id)

        with patch("src.api.routes.notifications.emit_event", new_callable=AsyncMock) as mock_emit:
            response = client.patch(
                f"/api/v1/notifications/{notification.id}/read",
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "notification:read"
        assert kwargs["data"]["id"] == notification.id
        assert kwargs["org_id"] == test_organization.id
        assert "exclude_user_id" not in kwargs

    def test_mark_all_read_emits_event(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        test_user: User,
        db: Session,
    ):
        """POST /notifications/read-all → emit_event called with 'notification:read_all'."""
        _make_notification(db, test_user.id, test_organization.id)
        _make_notification(db, test_user.id, test_organization.id)

        with patch("src.api.routes.notifications.emit_event", new_callable=AsyncMock) as mock_emit:
            response = client.post(
                "/api/v1/notifications/read-all",
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        assert kwargs["event_type"] == "notification:read_all"
        assert kwargs["org_id"] == test_organization.id
        assert "exclude_user_id" not in kwargs
