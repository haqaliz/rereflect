"""
TDD tests for the Jira inbound real-time webhook receiver
(status-sync-realtime-mapping/jira-webhook aspect, Phase 3).

Covers: POST /api/v1/webhooks/jira/inbound. Mirrors TestZendeskStatusChangeWebhook
in test_zendesk_webhook.py (status-change branch, fail-closed HMAC, idempotency)
and the per-org secret-matching pattern of test_linear_webhook.py.

# Acceptance-criteria traceability (spec.md):
# Signature verify: valid X-Hub-Signature -> processed; bad/missing -> 401;
#   missing stored secret -> 401 (fail-closed)
#   -> TestJiraWebhookSignatureEnforcement
# Unknown org (no secret matches) -> 401; unrelated event type -> 200 no-op
#   -> TestJiraWebhookRouteSkeleton
# Status-change event on a linked issue updates workflow_status per the
#   merged mapping + exactly one FeedbackWorkflowEvent (race-safe path)
#   -> TestJiraWebhookStatusChange
# Duplicate/stale delivery -> zero events (race guard)
#   -> TestJiraWebhookStatusChange::test_idempotency_two_deliveries_same_change_single_event
"""
import hashlib
import hmac
import json
import os
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.jira_integration import FeedbackJiraIssue, JiraIntegration
from src.models.organization import Organization
from src.utils.encryption import encrypt_api_key

# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

SITE_URL = "https://acme.atlassian.net"
EMAIL = "operator@acme.com"
WEBHOOK_SECRET_PLAIN = "whsec_jira_test_123"


def _make_jira_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _status_change_payload(
    issue_id="10001",
    issue_key="ENG-142",
    status_name="In Progress",
    category="indeterminate",
    include_status_changelog=True,
):
    changelog_items = []
    if include_status_changelog:
        changelog_items.append({
            "field": "status",
            "fieldtype": "jira",
            "fromString": "To Do",
            "toString": status_name,
        })
    return {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "id": str(issue_id),
            "key": issue_key,
            "fields": {
                "status": {
                    "name": status_name,
                    "statusCategory": {"key": category},
                },
            },
        },
        "changelog": {"items": changelog_items},
    }


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def _fernet_key_env():
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        yield


@pytest.fixture
def jira_integration(db: Session, test_organization: Organization) -> JiraIntegration:
    """Active JiraIntegration with a known decrypted webhook_secret, status sync ON."""
    integration = JiraIntegration(
        organization_id=test_organization.id,
        site_url=SITE_URL,
        email=EMAIL,
        api_token=encrypt_api_key("jira-api-token-abc"),
        webhook_secret=encrypt_api_key(WEBHOOK_SECRET_PLAIN),
        is_active=True,
        status_sync_enabled=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def jira_integration_no_secret(db: Session, test_organization: Organization) -> JiraIntegration:
    """Active JiraIntegration with webhook_secret=None (webhook never enabled)."""
    integration = JiraIntegration(
        organization_id=test_organization.id,
        site_url=SITE_URL,
        email=EMAIL,
        api_token=encrypt_api_key("jira-api-token-abc"),
        webhook_secret=None,
        is_active=True,
        status_sync_enabled=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def _make_feedback(db: Session, org_id: int, workflow_status="in_review") -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=org_id,
        text="Export crashes on large files",
        source="csv",
        workflow_status=workflow_status,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def _make_link(
    db: Session,
    org_id: int,
    feedback_id: int,
    jira_issue_id="10001",
    jira_issue_key="ENG-142",
    jira_status=None,
    jira_status_category=None,
) -> FeedbackJiraIssue:
    link = FeedbackJiraIssue(
        organization_id=org_id,
        feedback_id=feedback_id,
        jira_issue_id=jira_issue_id,
        jira_issue_key=jira_issue_key,
        jira_issue_url=f"{SITE_URL}/browse/{jira_issue_key}",
        jira_issue_title="Fix export crash",
        jira_status=jira_status,
        jira_status_category=jira_status_category,
        last_status_synced_at=datetime.utcnow() if jira_status_category else None,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _events_for(db: Session, feedback_id: int):
    return (
        db.query(FeedbackWorkflowEvent)
        .filter(FeedbackWorkflowEvent.feedback_id == feedback_id)
        .all()
    )


# ============================================================================
# Phase 1 — Pure helper unit tests (no TestClient, no DB)
# ============================================================================

class TestVerifyJiraSignature:
    def test_valid_signature_returns_true(self):
        from src.api.routes.jira_webhook import _verify_jira_signature

        body = b'{"issue": {"id": "1"}}'
        secret = "whsec_abc"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_jira_signature(body, sig, secret) is True

    def test_tampered_body_returns_false(self):
        from src.api.routes.jira_webhook import _verify_jira_signature

        body = b'{"issue": {"id": "1"}}'
        tampered = b'{"issue": {"id": "2"}}'
        secret = "whsec_abc"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_jira_signature(tampered, sig, secret) is False

    def test_missing_prefix_returns_false(self):
        from src.api.routes.jira_webhook import _verify_jira_signature

        body = b'{"issue": {"id": "1"}}'
        secret = "whsec_abc"
        raw_hex = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_jira_signature(body, raw_hex, secret) is False

    def test_empty_secret_returns_false_fail_closed(self):
        from src.api.routes.jira_webhook import _verify_jira_signature

        body = b'{"issue": {"id": "1"}}'
        sig = "sha256=" + hmac.new(b"whsec_abc", body, hashlib.sha256).hexdigest()

        assert _verify_jira_signature(body, sig, "") is False

    def test_none_secret_returns_false_fail_closed(self):
        from src.api.routes.jira_webhook import _verify_jira_signature

        assert _verify_jira_signature(b"{}", "sha256=abc", None) is False

    def test_missing_signature_returns_false(self):
        from src.api.routes.jira_webhook import _verify_jira_signature

        assert _verify_jira_signature(b"{}", "", "whsec_abc") is False

    def test_uses_hmac_compare_digest(self):
        from src.api.routes import jira_webhook

        body = b'{"issue": {"id": "1"}}'
        secret = "whsec_abc"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        with patch.object(jira_webhook.hmac, "compare_digest", wraps=jira_webhook.hmac.compare_digest) as mock_cmp:
            jira_webhook._verify_jira_signature(body, sig, secret)
            mock_cmp.assert_called_once()


# ============================================================================
# Phase 2 — Route skeleton + signature enforcement
# ============================================================================

class TestJiraWebhookRouteSkeleton:
    def test_missing_signature_header_401(self, client: TestClient):
        payload = _status_change_payload()
        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 401

    def test_no_matching_integration_401(self, client: TestClient):
        payload = _status_change_payload()
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, "some-secret-nobody-has")
        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 401

    def test_invalid_json_returns_400(self, client: TestClient, jira_integration: JiraIntegration):
        body = b"not-json-at-all{{{"
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)
        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 400

    def test_non_dict_json_returns_400(self, client: TestClient, jira_integration: JiraIntegration):
        body = b"[1, 2, 3]"
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)
        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 400


class TestJiraWebhookSignatureEnforcement:
    def test_tampered_body_rejected_401(self, client: TestClient, jira_integration: JiraIntegration):
        body_a = json.dumps(_status_change_payload(issue_id="1")).encode()
        body_b = json.dumps(_status_change_payload(issue_id="2")).encode()
        sig_for_a = _make_jira_signature(body_a, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body_b,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig_for_a},
        )
        assert response.status_code == 401

    def test_no_secret_configured_rejected_401_fail_closed(
        self, client: TestClient, jira_integration_no_secret: JiraIntegration
    ):
        payload = _status_change_payload()
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, "whatever-guessed-secret")

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 401

    def test_never_500s_on_corrupt_encrypted_secret(self, client: TestClient, jira_integration: JiraIntegration):
        payload = _status_change_payload()
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        with patch(
            "src.api.routes.jira_webhook.decrypt_api_key",
            side_effect=Exception("InvalidToken"),
        ):
            response = client.post(
                "/api/v1/webhooks/jira/inbound",
                content=body,
                headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
            )
        assert response.status_code == 401

    def test_response_never_leaks_secret(self, client: TestClient, jira_integration: JiraIntegration, db: Session):
        feedback = _make_feedback(db, jira_integration.organization_id)
        _make_link(db, jira_integration.organization_id, feedback.id, jira_status_category="new")

        payload = _status_change_payload()
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert WEBHOOK_SECRET_PLAIN not in response.text
        assert sig not in response.text


# ============================================================================
# Phase 3 — Event discrimination (non-status events are 200 no-ops)
# ============================================================================

class TestJiraWebhookEventDiscrimination:
    def test_non_issue_updated_event_is_200_noop(self, client: TestClient, jira_integration: JiraIntegration):
        payload = {"webhookEvent": "jira:issue_created", "issue": {"id": "10001"}}
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_issue_updated_without_status_changelog_is_200_noop(
        self, client: TestClient, jira_integration: JiraIntegration
    ):
        payload = _status_change_payload(include_status_changelog=False)
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


# ============================================================================
# Phase 4 — Status-change reconcile
# ============================================================================

class TestJiraWebhookStatusChange:
    def test_verified_status_event_moves_feedback_one_event(
        self, client: TestClient, jira_integration: JiraIntegration, db: Session
    ):
        feedback = _make_feedback(db, jira_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            jira_integration.organization_id,
            feedback.id,
            jira_issue_id="10001",
            jira_status="To Do",
            jira_status_category="new",
        )

        payload = _status_change_payload(issue_id="10001", status_name="Done", category="done")
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        events = _events_for(db, feedback.id)
        assert len(events) == 1
        assert events[0].event_type == "status_changed"
        assert events[0].old_value == "new"
        assert events[0].new_value == "resolved"
        assert events[0].metadata_["source"] == "jira"
        assert events[0].metadata_["jira_status"] == "Done"
        assert events[0].metadata_["jira_issue_key"] == "ENG-142"

    def test_status_sync_disabled_acks_200_no_change_no_event(
        self, client: TestClient, jira_integration: JiraIntegration, db: Session
    ):
        jira_integration.status_sync_enabled = False
        db.commit()
        feedback = _make_feedback(db, jira_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            jira_integration.organization_id,
            feedback.id,
            jira_issue_id="10001",
            jira_status="To Do",
            jira_status_category="new",
        )

        payload = _status_change_payload(issue_id="10001", status_name="Done", category="done")
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "new"
        assert _events_for(db, feedback.id) == []

    def test_first_observation_via_webhook_seeds_no_apply(
        self, client: TestClient, jira_integration: JiraIntegration, db: Session
    ):
        feedback = _make_feedback(db, jira_integration.organization_id, workflow_status="new")
        _make_link(db, jira_integration.organization_id, feedback.id, jira_issue_id="10001")

        payload = _status_change_payload(issue_id="10001", status_name="In Progress", category="indeterminate")
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "new"
        assert _events_for(db, feedback.id) == []

        link = db.query(FeedbackJiraIssue).filter(FeedbackJiraIssue.feedback_id == feedback.id).first()
        assert link.jira_status_category == "indeterminate"

    def test_unlinked_issue_is_200_noop(self, client: TestClient, jira_integration: JiraIntegration, db: Session):
        payload = _status_change_payload(issue_id="99999", status_name="Done", category="done")
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200
        assert db.query(FeedbackWorkflowEvent).count() == 0

    def test_idempotency_two_deliveries_same_change_single_event(
        self, client: TestClient, jira_integration: JiraIntegration, db: Session
    ):
        """Webhook redelivered on the SAME change must result in exactly one
        status_changed event total -- the second reconcile sees fetched ==
        already-stored category -> noop (race guard / idempotency window)."""
        feedback = _make_feedback(db, jira_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            jira_integration.organization_id,
            feedback.id,
            jira_issue_id="10001",
            jira_status="To Do",
            jira_status_category="new",
        )

        payload = _status_change_payload(issue_id="10001", status_name="Done", category="done")
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)
        headers = {"Content-Type": "application/json", "X-Hub-Signature": sig}

        response1 = client.post("/api/v1/webhooks/jira/inbound", content=body, headers=headers)
        response2 = client.post("/api/v1/webhooks/jira/inbound", content=body, headers=headers)

        assert response1.status_code == 200
        assert response2.status_code == 200
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"
        assert len(_events_for(db, feedback.id)) == 1

    def test_multi_issue_feedback_most_advanced_category_wins(
        self, client: TestClient, jira_integration: JiraIntegration, db: Session
    ):
        """A feedback item linked to two Jira issues: one moves to 'done',
        the other stays 'indeterminate' -- most_advanced picks 'done'."""
        feedback = _make_feedback(db, jira_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            jira_integration.organization_id,
            feedback.id,
            jira_issue_id="10001",
            jira_issue_key="ENG-142",
            jira_status="To Do",
            jira_status_category="new",
        )
        _make_link(
            db,
            jira_integration.organization_id,
            feedback.id,
            jira_issue_id="10002",
            jira_issue_key="ENG-143",
            jira_status="In Progress",
            jira_status_category="indeterminate",
        )

        payload = _status_change_payload(issue_id="10001", issue_key="ENG-142", status_name="Done", category="done")
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"
        assert len(_events_for(db, feedback.id)) == 1

    def test_custom_status_mapping_is_honored(
        self, client: TestClient, jira_integration: JiraIntegration, db: Session
    ):
        jira_integration.status_mapping = {"done": "closed"}
        db.commit()

        feedback = _make_feedback(db, jira_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            jira_integration.organization_id,
            feedback.id,
            jira_issue_id="10001",
            jira_status="To Do",
            jira_status_category="new",
        )

        payload = _status_change_payload(issue_id="10001", status_name="Done", category="done")
        body = json.dumps(payload).encode()
        sig = _make_jira_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/jira/inbound",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "closed"
