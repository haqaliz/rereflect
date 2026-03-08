"""
TDD tests for Linear webhook receiver (Task #5).

Tests cover:
1. Route exists at POST /api/v1/webhooks/linear/inbound
2. Signature verification (reject missing/invalid, accept valid)
3. Ignores non-Issue event types
4. Looks up FeedbackLinearIssue by linear_issue_id
5. Updates linear_status, linear_assignee, linear_priority on the link record
6. Status mapping lookup -> updates feedback.workflow_status
7. Timeline entry created (FeedbackWorkflowEvent) on status change
8. Idempotency: same status twice -> no duplicate timeline entry
9. Returns 200 for unknown linear_issue_id (graceful no-op)
"""
import hashlib
import hmac
import json
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem
from src.api.auth import hash_password


WEBHOOK_SECRET = "wh_test_secret_abc123"
WEBHOOK_URL = "/api/v1/webhooks/linear/inbound"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_linear_signature(body: bytes, secret: str) -> str:
    """Compute Linear webhook HMAC-SHA256 signature."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


_SENTINEL = object()


def issue_update_payload(
    issue_id: str = "lin-issue-uuid-1",
    identifier: str = "ENG-142",
    state_name: str = "In Progress",
    state_type: str = "started",
    assignee_name=_SENTINEL,
    priority: int = 2,
) -> dict:
    if assignee_name is _SENTINEL:
        assignee_name = "Jane Doe"
    return {
        "type": "Issue",
        "action": "update",
        "data": {
            "id": issue_id,
            "identifier": identifier,
            "title": "Fix CSV export timeout",
            "state": {
                "id": "state-uuid-1",
                "name": state_name,
                "type": state_type,
            },
            "assignee": {"name": assignee_name} if assignee_name else None,
            "priority": priority,
        },
        "updatedFrom": {
            "stateId": "state-uuid-old",
        },
    }


def post_webhook(
    client: TestClient,
    payload: dict,
    secret: str = WEBHOOK_SECRET,
    bad_sig: bool = False,
    omit_sig: bool = False,
) -> object:
    body = json.dumps(payload).encode()
    sig = "bad_signature" if bad_sig else make_linear_signature(body, secret)
    headers = {"Content-Type": "application/json"}
    if not omit_sig:
        headers["Linear-Signature"] = sig
    return client.post(WEBHOOK_URL, content=body, headers=headers)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Pro Org", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_org: Organization) -> User:
    user = User(
        email="user@pro.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def feedback(db: Session, pro_org: Organization) -> FeedbackItem:
    item = FeedbackItem(
        organization_id=pro_org.id,
        text="CSV export breaks on large datasets",
        workflow_status="new",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def linear_integration(db: Session, pro_org: Organization, pro_user: User):
    from src.models.linear_integration import LinearIntegration
    integration = LinearIntegration(
        organization_id=pro_org.id,
        access_token="enc_token",
        linear_org_id="lin_org_1",
        linear_org_name="Pro Org Linear",
        connected_by_user_id=pro_user.id,
        is_active=True,
        webhook_secret=WEBHOOK_SECRET,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def linked_issue(db: Session, pro_org: Organization, pro_user: User, feedback: FeedbackItem):
    from src.models.linear_integration import FeedbackLinearIssue
    issue = FeedbackLinearIssue(
        organization_id=pro_org.id,
        feedback_id=feedback.id,
        linear_issue_id="lin-issue-uuid-1",
        linear_issue_identifier="ENG-142",
        linear_issue_url="https://linear.app/org/issue/ENG-142",
        linear_issue_title="Fix CSV export timeout",
        linear_status="Backlog",
        created_by_user_id=pro_user.id,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


@pytest.fixture
def status_mappings(db: Session, pro_org: Organization):
    from src.models.linear_integration import LinearStatusMapping
    defaults = [
        ("backlog", "Backlog", "new"),
        ("unstarted", "Todo", "new"),
        ("started", "In Progress", "in_review"),
        ("completed", "Done", "resolved"),
        ("canceled", "Cancelled", "closed"),
    ]
    mappings = []
    for status_type, status_name, rr_status in defaults:
        m = LinearStatusMapping(
            organization_id=pro_org.id,
            linear_status_type=status_type,
            linear_status_name=status_name,
            rereflect_status=rr_status,
        )
        db.add(m)
        mappings.append(m)
    db.commit()
    return mappings


# ---------------------------------------------------------------------------
# 1. Route existence
# ---------------------------------------------------------------------------
class TestWebhookRouteExists:

    def test_route_exists_returns_not_404(self, client: TestClient, linear_integration):
        """Endpoint exists — any response other than 404 means route is registered."""
        payload = issue_update_payload()
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Linear-Signature": make_linear_signature(body, WEBHOOK_SECRET),
        }
        response = client.post(WEBHOOK_URL, content=body, headers=headers)
        assert response.status_code != 404, "Webhook route is not registered"

    def test_get_returns_405(self, client: TestClient):
        """GET method not allowed."""
        response = client.get(WEBHOOK_URL)
        assert response.status_code in (404, 405)


# ---------------------------------------------------------------------------
# 2. Signature verification
# ---------------------------------------------------------------------------
class TestSignatureVerification:

    def test_missing_signature_returns_401(self, client: TestClient, linear_integration):
        payload = issue_update_payload()
        response = post_webhook(client, payload, omit_sig=True)
        assert response.status_code == 401

    def test_invalid_signature_returns_401(self, client: TestClient, linear_integration):
        payload = issue_update_payload()
        response = post_webhook(client, payload, bad_sig=True)
        assert response.status_code == 401

    def test_valid_signature_passes(
        self, client: TestClient, linear_integration, linked_issue, status_mappings
    ):
        payload = issue_update_payload()
        response = post_webhook(client, payload)
        assert response.status_code == 200

    def test_signature_from_wrong_secret_returns_401(self, client: TestClient, linear_integration):
        payload = issue_update_payload()
        response = post_webhook(client, payload, secret="wrong_secret_xyz")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# 3. Non-Issue event types ignored
# ---------------------------------------------------------------------------
class TestNonIssueEventsIgnored:

    def test_comment_event_ignored(self, client: TestClient, linear_integration):
        payload = {
            "type": "Comment",
            "action": "create",
            "data": {"id": "comment-1", "body": "Looking into this"},
        }
        response = post_webhook(client, payload)
        assert response.status_code == 200
        body = response.json()
        assert "ignored" in str(body).lower() or body.get("status") in ("ignored", "ok")

    def test_project_event_ignored(self, client: TestClient, linear_integration):
        payload = {
            "type": "Project",
            "action": "update",
            "data": {"id": "project-1", "name": "Q2 Roadmap"},
        }
        response = post_webhook(client, payload)
        assert response.status_code == 200

    def test_create_action_ignored(self, client: TestClient, linear_integration):
        """Issue 'create' action (not 'update') should be ignored for status sync."""
        payload = {
            "type": "Issue",
            "action": "create",
            "data": {
                "id": "lin-issue-new",
                "identifier": "ENG-200",
                "title": "New issue",
                "state": {"id": "s1", "name": "Backlog", "type": "backlog"},
                "priority": 0,
            },
        }
        response = post_webhook(client, payload)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 4. Unknown linear_issue_id — graceful no-op
# ---------------------------------------------------------------------------
class TestUnknownIssueId:

    def test_unknown_issue_id_returns_200(self, client: TestClient, linear_integration, status_mappings):
        payload = issue_update_payload(issue_id="unknown-issue-uuid-999")
        response = post_webhook(client, payload)
        assert response.status_code == 200

    def test_unknown_issue_id_no_crash(self, client: TestClient, linear_integration):
        """Even without status_mappings, unknown issue_id should not crash."""
        payload = issue_update_payload(issue_id="totally-unknown-uuid")
        response = post_webhook(client, payload)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# 5. FeedbackLinearIssue fields updated
# ---------------------------------------------------------------------------
class TestLinkedIssueFieldsUpdated:

    def test_linear_status_updated(
        self, client: TestClient, db: Session, linear_integration, linked_issue, status_mappings
    ):
        from src.models.linear_integration import FeedbackLinearIssue
        payload = issue_update_payload(state_name="In Progress", state_type="started")
        response = post_webhook(client, payload)
        assert response.status_code == 200

        db.expire_all()
        issue = db.query(FeedbackLinearIssue).filter_by(id=linked_issue.id).first()
        assert issue.linear_status == "In Progress"

    def test_linear_assignee_updated(
        self, client: TestClient, db: Session, linear_integration, linked_issue, status_mappings
    ):
        from src.models.linear_integration import FeedbackLinearIssue
        payload = issue_update_payload(assignee_name="Bob Smith")
        response = post_webhook(client, payload)
        assert response.status_code == 200

        db.expire_all()
        issue = db.query(FeedbackLinearIssue).filter_by(id=linked_issue.id).first()
        assert issue.linear_assignee == "Bob Smith"

    def test_linear_priority_updated(
        self, client: TestClient, db: Session, linear_integration, linked_issue, status_mappings
    ):
        from src.models.linear_integration import FeedbackLinearIssue
        payload = issue_update_payload(priority=1)
        response = post_webhook(client, payload)
        assert response.status_code == 200

        db.expire_all()
        issue = db.query(FeedbackLinearIssue).filter_by(id=linked_issue.id).first()
        assert issue.linear_priority == 1

    def test_assignee_set_then_updated(
        self, client: TestClient, db: Session, linear_integration, linked_issue, status_mappings
    ):
        """Assignee is set on first webhook, then updated on second."""
        from src.models.linear_integration import FeedbackLinearIssue
        # First: set assignee to Jane
        post_webhook(client, issue_update_payload(assignee_name="Jane Doe"))
        db.expire_all()
        issue = db.query(FeedbackLinearIssue).filter_by(id=linked_issue.id).first()
        assert issue.linear_assignee == "Jane Doe"

        # Second: update assignee to Bob
        post_webhook(client, issue_update_payload(assignee_name="Bob Smith"))
        db.expire_all()
        issue = db.query(FeedbackLinearIssue).filter_by(id=linked_issue.id).first()
        assert issue.linear_assignee == "Bob Smith"


# ---------------------------------------------------------------------------
# 6. Feedback workflow_status updated via status mapping
# ---------------------------------------------------------------------------
class TestFeedbackStatusSync:

    def test_started_maps_to_in_review(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        payload = issue_update_payload(state_name="In Progress", state_type="started")
        response = post_webhook(client, payload)
        assert response.status_code == 200

        db.expire_all()
        updated = db.query(FeedbackItem).filter_by(id=feedback.id).first()
        assert updated.workflow_status == "in_review"

    def test_completed_maps_to_resolved(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        payload = issue_update_payload(state_name="Done", state_type="completed")
        response = post_webhook(client, payload)
        assert response.status_code == 200

        db.expire_all()
        updated = db.query(FeedbackItem).filter_by(id=feedback.id).first()
        assert updated.workflow_status == "resolved"

    def test_canceled_maps_to_closed(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        payload = issue_update_payload(state_name="Cancelled", state_type="canceled")
        response = post_webhook(client, payload)
        assert response.status_code == 200

        db.expire_all()
        updated = db.query(FeedbackItem).filter_by(id=feedback.id).first()
        assert updated.workflow_status == "closed"

    def test_backlog_maps_to_new(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        # First move to "started" so linked_issue.linear_status changes away from "Backlog"
        payload_started = issue_update_payload(state_name="In Progress", state_type="started")
        post_webhook(client, payload_started)
        db.expire_all()

        # Now move back to backlog — status_changed will be True ("In Progress" -> "Backlog")
        payload_backlog = issue_update_payload(state_name="Backlog", state_type="backlog")
        response = post_webhook(client, payload_backlog)
        assert response.status_code == 200

        db.expire_all()
        updated = db.query(FeedbackItem).filter_by(id=feedback.id).first()
        assert updated.workflow_status == "new"

    def test_no_status_mapping_does_not_crash(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback
    ):
        """No status_mappings configured -> webhook still 200, feedback status unchanged."""
        original_status = feedback.workflow_status
        payload = issue_update_payload(state_name="In Progress", state_type="started")
        response = post_webhook(client, payload)
        assert response.status_code == 200

        db.expire_all()
        updated = db.query(FeedbackItem).filter_by(id=feedback.id).first()
        assert updated.workflow_status == original_status


# ---------------------------------------------------------------------------
# 7. Timeline entry (FeedbackWorkflowEvent) created on status change
# ---------------------------------------------------------------------------
class TestTimelineEntry:

    def test_timeline_entry_created_on_status_change(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        from src.models.feedback_workflow_event import FeedbackWorkflowEvent
        before_count = db.query(FeedbackWorkflowEvent).filter_by(feedback_id=feedback.id).count()

        payload = issue_update_payload(state_name="Done", state_type="completed")
        response = post_webhook(client, payload)
        assert response.status_code == 200

        db.expire_all()
        after_count = db.query(FeedbackWorkflowEvent).filter_by(feedback_id=feedback.id).count()
        assert after_count == before_count + 1

    def test_timeline_entry_event_type(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        from src.models.feedback_workflow_event import FeedbackWorkflowEvent
        payload = issue_update_payload(state_name="Done", state_type="completed")
        post_webhook(client, payload)

        db.expire_all()
        event = db.query(FeedbackWorkflowEvent).filter_by(
            feedback_id=feedback.id
        ).order_by(FeedbackWorkflowEvent.id.desc()).first()
        assert event is not None
        assert event.event_type in ("status_changed", "linear_status_changed", "linear_sync")

    def test_timeline_entry_records_new_status(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        from src.models.feedback_workflow_event import FeedbackWorkflowEvent
        payload = issue_update_payload(state_name="Done", state_type="completed")
        post_webhook(client, payload)

        db.expire_all()
        event = db.query(FeedbackWorkflowEvent).filter_by(
            feedback_id=feedback.id
        ).order_by(FeedbackWorkflowEvent.id.desc()).first()
        assert event is not None
        assert event.new_value is not None
        # new_value should reference "resolved" or "Done"
        assert "resolved" in (event.new_value or "").lower() or "done" in (event.new_value or "").lower()

    def test_no_timeline_entry_for_unknown_issue(
        self, client: TestClient, db: Session, linear_integration, feedback, status_mappings
    ):
        from src.models.feedback_workflow_event import FeedbackWorkflowEvent
        before_count = db.query(FeedbackWorkflowEvent).filter_by(feedback_id=feedback.id).count()

        payload = issue_update_payload(issue_id="totally-unknown-uuid")
        post_webhook(client, payload)

        db.expire_all()
        after_count = db.query(FeedbackWorkflowEvent).filter_by(feedback_id=feedback.id).count()
        assert after_count == before_count


# ---------------------------------------------------------------------------
# 8. Idempotency
# ---------------------------------------------------------------------------
class TestIdempotency:

    def test_same_status_twice_no_duplicate_timeline(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        from src.models.feedback_workflow_event import FeedbackWorkflowEvent
        payload = issue_update_payload(state_name="Done", state_type="completed")

        post_webhook(client, payload)
        db.expire_all()
        count_after_first = db.query(FeedbackWorkflowEvent).filter_by(feedback_id=feedback.id).count()

        post_webhook(client, payload)
        db.expire_all()
        count_after_second = db.query(FeedbackWorkflowEvent).filter_by(feedback_id=feedback.id).count()

        assert count_after_second == count_after_first, "Duplicate timeline entry on identical webhook replay"

    def test_same_status_twice_feedback_status_stable(
        self, client: TestClient, db: Session, linear_integration, linked_issue, feedback, status_mappings
    ):
        payload = issue_update_payload(state_name="Done", state_type="completed")
        post_webhook(client, payload)
        post_webhook(client, payload)

        db.expire_all()
        updated = db.query(FeedbackItem).filter_by(id=feedback.id).first()
        assert updated.workflow_status == "resolved"
