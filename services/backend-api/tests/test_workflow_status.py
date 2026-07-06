"""
Characterization tests for POST /api/v1/workflow/status.

These lock the CURRENT behavior of the internal bulk status-change route so
that the upcoming service-helper extraction (apply_status_change /
dispatch_status_webhooks) cannot change observable behavior:

  * A real status change creates exactly one FeedbackWorkflowEvent
    (event_type="status_changed", correct old/new, actor_id=current_user.id),
    sets workflow_status, and calls the webhook dispatcher with
    event_type="feedback.status_changed" and changed_by=<user.email>.
  * A same-status change is a no-op: no event, no webhook (idempotency).
"""

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.organization import Organization
from src.models.user import User


def _make_feedback(db: Session, org: Organization, status: str = "new") -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org.id,
        text="Payment failed on checkout.",
        source="email",
        sentiment_label="negative",
        sentiment_score=-0.7,
        is_urgent=False,
        workflow_status=status,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


class TestStatusChangeCharacterization:
    """POST /api/v1/workflow/status — current behavior baseline."""

    def test_real_status_change_creates_event_and_dispatches_webhook(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        fb = _make_feedback(db, test_organization, status="new")

        with patch(
            "src.services.webhook_dispatcher.dispatch_webhook_event"
        ) as mock_dispatch:
            response = client.post(
                "/api/v1/workflow/status",
                json={"feedback_ids": [fb.id], "new_status": "resolved"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json() == {"updated": 1}

        # workflow_status is persisted
        db.refresh(fb)
        assert fb.workflow_status == "resolved"

        # exactly one status_changed timeline event with correct fields
        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(
                FeedbackWorkflowEvent.feedback_id == fb.id,
                FeedbackWorkflowEvent.event_type == "status_changed",
            )
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.old_value == "new"
        assert event.new_value == "resolved"
        assert event.actor_id == test_user.id
        assert event.organization_id == test_organization.id

        # webhook dispatcher called once with the expected payload
        assert mock_dispatch.call_count == 1
        _, kwargs = mock_dispatch.call_args
        assert kwargs["event_type"] == "feedback.status_changed"
        assert kwargs["org_id"] == test_organization.id
        assert kwargs["feedback"].id == fb.id
        assert kwargs["changes"]["old_status"] == "new"
        assert kwargs["changes"]["new_status"] == "resolved"
        assert kwargs["changes"]["changed_by"] == test_user.email

    def test_same_status_change_is_noop(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        fb = _make_feedback(db, test_organization, status="resolved")

        with patch(
            "src.services.webhook_dispatcher.dispatch_webhook_event"
        ) as mock_dispatch:
            response = client.post(
                "/api/v1/workflow/status",
                json={"feedback_ids": [fb.id], "new_status": "resolved"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json() == {"updated": 0}

        # no timeline event created
        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == fb.id)
            .all()
        )
        assert len(events) == 0

        # no webhook dispatched
        assert mock_dispatch.call_count == 0
