"""
TDD tests for webhook_dispatcher service (M3.1 Phase 2).

Tests are written first; the implementation must make them pass.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

# Ensure encryption key is available for Fernet
os.environ.setdefault(
    "LLM_ENCRYPTION_KEY",
    "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY=",
)

from sqlalchemy.orm import Session

from src.models.webhook_endpoint import WebhookEndpoint
from src.models.webhook_delivery import WebhookDelivery
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.utils.encryption import encrypt_api_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_webhook(
    db: Session,
    org_id: int,
    events: list,
    category_filters: list = None,
    is_active: bool = True,
    retry_mode: str = "fire_and_forget",
) -> WebhookEndpoint:
    """Create and persist a WebhookEndpoint for testing."""
    wh = WebhookEndpoint(
        organization_id=org_id,
        name="Test Webhook",
        url="https://example.com/hook",
        signing_secret=encrypt_api_key("secret123"),
        events=events,
        category_filters=category_filters or [],
        retry_mode=retry_mode,
        is_active=is_active,
        consecutive_failures=0,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


def _make_feedback(
    db: Session,
    org_id: int,
    tags: list = None,
    is_urgent: bool = False,
    workflow_status: str = "new",
) -> FeedbackItem:
    """Create and persist a FeedbackItem for testing."""
    fb = FeedbackItem(
        organization_id=org_id,
        text="Some feedback text",
        source="manual",
        sentiment_label="neutral",
        sentiment_score=0.0,
        tags=tags or [],
        is_urgent=is_urgent,
        workflow_status=workflow_status,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDispatchMatchesWebhooksByEvent:
    """dispatch_webhook_event fires only webhooks subscribed to the given event."""

    def test_dispatch_matches_webhooks_by_event(self, db: Session, test_organization: Organization):
        """
        Given two webhooks — one subscribed to feedback.created, one to feedback.analyzed —
        dispatching feedback.created should only enqueue a task for the first webhook.
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        wh_created = _make_webhook(db, test_organization.id, events=["feedback.created"])
        wh_analyzed = _make_webhook(db, test_organization.id, events=["feedback.analyzed"])

        feedback = _make_feedback(db, test_organization.id)

        enqueued = []

        def fake_enqueue(webhook_id, payload):
            enqueued.append(webhook_id)

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=fake_enqueue,
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.created",
                feedback=feedback,
            )

        assert len(enqueued) == 1
        assert enqueued[0] == wh_created.id


class TestDispatchSkipsInactiveWebhooks:
    """dispatch_webhook_event skips webhooks that are not active."""

    def test_dispatch_skips_inactive_webhooks(self, db: Session, test_organization: Organization):
        """
        An inactive webhook subscribed to the event should NOT be enqueued.
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        _make_webhook(
            db, test_organization.id,
            events=["feedback.created"],
            is_active=False,
        )
        feedback = _make_feedback(db, test_organization.id)

        enqueued = []

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=lambda wid, payload: enqueued.append(wid),
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.created",
                feedback=feedback,
            )

        assert enqueued == []


class TestDispatchCategoryMatchFiltersByTags:
    """For feedback.category_match, only webhooks whose filters intersect feedback.tags fire."""

    def test_matching_tags_fires(self, db: Session, test_organization: Organization):
        """
        Webhook with category_filters=["billing"], feedback.tags=["billing", "ui"] → match.
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        wh = _make_webhook(
            db, test_organization.id,
            events=["feedback.category_match"],
            category_filters=["billing"],
        )
        feedback = _make_feedback(db, test_organization.id, tags=["billing", "ui"])

        enqueued = []

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=lambda wid, payload: enqueued.append(wid),
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.category_match",
                feedback=feedback,
            )

        assert wh.id in enqueued

    def test_non_matching_tags_does_not_fire(self, db: Session, test_organization: Organization):
        """
        Webhook with category_filters=["billing"], feedback.tags=["ui"] → no match.
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        _make_webhook(
            db, test_organization.id,
            events=["feedback.category_match"],
            category_filters=["billing"],
        )
        feedback = _make_feedback(db, test_organization.id, tags=["ui"])

        enqueued = []

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=lambda wid, payload: enqueued.append(wid),
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.category_match",
                feedback=feedback,
            )

        assert enqueued == []

    def test_empty_category_filters_fires_always(self, db: Session, test_organization: Organization):
        """
        A webhook subscribed to feedback.category_match with no category_filters
        fires for any feedback (no-filter = match-all).
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        wh = _make_webhook(
            db, test_organization.id,
            events=["feedback.category_match"],
            category_filters=[],  # no filter ⇒ match all
        )
        feedback = _make_feedback(db, test_organization.id, tags=["ui"])

        enqueued = []

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=lambda wid, payload: enqueued.append(wid),
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.category_match",
                feedback=feedback,
            )

        assert wh.id in enqueued


class TestDispatchBuildsCorrectPayload:
    """The payload passed to _enqueue_delivery must match the PRD schema."""

    def test_dispatch_builds_correct_payload(self, db: Session, test_organization: Organization):
        """
        The enqueued payload must include: event, timestamp, webhook_id,
        organization_id, data.feedback with all required fields.
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        wh = _make_webhook(db, test_organization.id, events=["feedback.created"])
        feedback = _make_feedback(
            db, test_organization.id,
            tags=["auth", "bug"],
            is_urgent=True,
        )
        feedback.sentiment_label = "negative"
        feedback.sentiment_score = -0.85
        feedback.churn_risk_score = 60
        feedback.pain_point_category = "authentication"
        feedback.feature_request_category = None
        feedback.customer_email = "user@example.com"
        feedback.source = "slack"
        db.commit()

        captured = {}

        def fake_enqueue(webhook_id, payload):
            captured[webhook_id] = payload

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=fake_enqueue,
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.created",
                feedback=feedback,
            )

        assert wh.id in captured
        payload = captured[wh.id]

        # Top-level keys
        assert payload["event"] == "feedback.created"
        assert "timestamp" in payload
        assert payload["webhook_id"] == wh.id
        assert payload["organization_id"] == test_organization.id

        # data.feedback
        fb_data = payload["data"]["feedback"]
        assert fb_data["id"] == feedback.id
        assert fb_data["text"] == feedback.text
        assert fb_data["sentiment_label"] == "negative"
        assert fb_data["sentiment_score"] == -0.85
        assert fb_data["tags"] == ["auth", "bug"]
        assert fb_data["is_urgent"] is True
        assert fb_data["churn_risk_score"] == 60
        assert fb_data["pain_point_category"] == "authentication"
        assert fb_data["feature_request_category"] is None
        assert fb_data["workflow_status"] == feedback.workflow_status
        assert fb_data["customer_email"] == "user@example.com"
        assert fb_data["source"] == "slack"
        assert "created_at" in fb_data

        # For feedback.created, no 'changes' or 'matched_categories' at top level
        assert "changes" not in payload["data"]
        assert "matched_categories" not in payload["data"]


class TestDispatchStatusChangedIncludesChanges:
    """For feedback.status_changed events, payload.data.changes is populated."""

    def test_dispatch_status_changed_includes_changes(self, db: Session, test_organization: Organization):
        """
        When event_type='feedback.status_changed' and changes dict is provided,
        payload.data.changes must include old_status, new_status, changed_by.
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        wh = _make_webhook(db, test_organization.id, events=["feedback.status_changed"])
        feedback = _make_feedback(db, test_organization.id)

        changes = {
            "old_status": "new",
            "new_status": "in_review",
            "changed_by": "admin@company.com",
        }

        captured = {}

        def fake_enqueue(webhook_id, payload):
            captured[webhook_id] = payload

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=fake_enqueue,
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.status_changed",
                feedback=feedback,
                changes=changes,
            )

        assert wh.id in captured
        payload = captured[wh.id]
        assert payload["data"]["changes"] == changes


class TestDispatchCategoryMatchIncludesMatchedCategories:
    """For feedback.category_match, payload.data.matched_categories is populated."""

    def test_dispatch_category_match_includes_matched_categories(
        self, db: Session, test_organization: Organization
    ):
        """
        Matched categories (intersection of webhook.category_filters and feedback.tags)
        should appear in payload.data.matched_categories.
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        wh = _make_webhook(
            db, test_organization.id,
            events=["feedback.category_match"],
            category_filters=["billing", "auth"],
        )
        feedback = _make_feedback(db, test_organization.id, tags=["auth", "ui"])

        captured = {}

        def fake_enqueue(webhook_id, payload):
            captured[webhook_id] = payload

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=fake_enqueue,
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.category_match",
                feedback=feedback,
            )

        assert wh.id in captured
        payload = captured[wh.id]
        assert "matched_categories" in payload["data"]
        assert set(payload["data"]["matched_categories"]) == {"auth"}


class TestDispatchIsolatesOrganizations:
    """Webhooks from other organizations should never be triggered."""

    def test_dispatch_does_not_cross_org_boundaries(
        self, db: Session, test_organization: Organization
    ):
        """
        A webhook belonging to a different org should not fire even if it
        matches the event type.
        """
        from src.services.webhook_dispatcher import dispatch_webhook_event

        # Create a second organization
        other_org = Organization(name="Other Corp", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        # Webhook belongs to other_org
        _make_webhook(db, other_org.id, events=["feedback.created"])
        # Feedback belongs to test_organization
        feedback = _make_feedback(db, test_organization.id)

        enqueued = []

        with patch(
            "src.services.webhook_dispatcher._enqueue_delivery",
            side_effect=lambda wid, payload: enqueued.append(wid),
        ):
            dispatch_webhook_event(
                db=db,
                org_id=test_organization.id,
                event_type="feedback.created",
                feedback=feedback,
            )

        assert enqueued == []
