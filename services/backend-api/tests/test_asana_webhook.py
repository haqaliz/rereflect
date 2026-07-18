"""
TDD tests for the Asana inbound real-time webhook receiver
(status-sync-realtime-mapping/asana-webhook aspect, Phase 3).

Covers: POST /api/v1/webhooks/asana/inbound/{webhook_url_token}. Mirrors
TestJiraWebhookStatusChange in test_jira_webhook.py (fail-closed HMAC,
reconcile, idempotency) PLUS the Asana-specific handshake branch (no Jira
analog): the first POST carries `X-Hook-Secret` and must be persisted +
echoed, 200, no reconcile.

SECURITY (sec review, CRITICAL): the integration is resolved by an
unguessable `webhook_url_token` (secrets.token_urlsafe(32), unique index) --
NOT the guessable integer `integration_id` -- and the handshake branch is
gated: it is only ever allowed to persist a secret when
`integration.webhook_secret is None` (i.e. no handshake has completed yet,
or POST /webhook/enable has just reset it to None for a fresh handshake).
An org that already has a stored secret rejects ANY re-handshake attempt
with 401 and leaves the stored secret untouched -- this closes both the
integer-id enumeration attack AND the handshake-overwrite race that would
otherwise let an unauthenticated attacker set a known secret for any active
org and forge signed events.

# Acceptance-criteria traceability (spec.md):
# Handshake: first request with X-Hook-Secret and no stored secret ->
#   secret persisted (encrypted) + echoed in response header, 200, no
#   reconcile -> TestAsanaWebhookHandshake
# No-overwrite gate: a request with X-Hook-Secret against an org that
#   already has a stored secret -> 401, secret unchanged (sec review)
#   -> TestAsanaWebhookHandshake
# Signature verify: valid X-Hook-Signature -> processed; bad/missing -> 401;
#   missing stored secret -> 401 (fail-closed)
#   -> TestAsanaWebhookSignatureEnforcement
# A completion change on a linked task updates workflow_status per the
#   merged mapping + exactly one FeedbackWorkflowEvent (race-safe path)
#   -> TestAsanaWebhookCompletionChange
# Stale/duplicate delivery -> zero events (race guard)
#   -> TestAsanaWebhookCompletionChange::test_idempotency_two_deliveries_same_change_single_event
"""
import hashlib
import hmac
import json
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.asana_integration import AsanaIntegration, FeedbackAsanaTask
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.organization import Organization
from src.utils.encryption import encrypt_api_key

# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

WEBHOOK_SECRET_PLAIN = "whsec_asana_test_123"
WEBHOOK_URL_TOKEN = "test-url-token-abc123-unguessable"
WEBHOOK_URL_TOKEN_NO_SECRET = "test-url-token-no-secret-456-unguessable"


def _make_asana_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _completion_event_payload(task_gid="1300000000001", completed=True):
    return {
        "events": [
            {
                "user": {"gid": "999", "resource_type": "user"},
                "created_at": "2026-07-18T00:00:00.000Z",
                "action": "changed",
                "resource": {"gid": task_gid, "resource_type": "task"},
                "parent": None,
                "change": {
                    "field": "completed",
                    "action": "changed",
                    "new_value": completed,
                    "added_value": None,
                    "removed_value": None,
                },
            }
        ]
    }


def _non_completion_event_payload(task_gid="1300000000001"):
    return {
        "events": [
            {
                "user": {"gid": "999", "resource_type": "user"},
                "created_at": "2026-07-18T00:00:00.000Z",
                "action": "changed",
                "resource": {"gid": task_gid, "resource_type": "task"},
                "parent": None,
                "change": {
                    "field": "name",
                    "action": "changed",
                    "new_value": "Renamed task",
                    "added_value": None,
                    "removed_value": None,
                },
            }
        ]
    }


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def _fernet_key_env():
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        yield


@pytest.fixture
def asana_integration(db: Session, test_organization: Organization) -> AsanaIntegration:
    """Active AsanaIntegration with a known decrypted webhook_secret, status sync ON."""
    integration = AsanaIntegration(
        organization_id=test_organization.id,
        api_token=encrypt_api_key("asana-pat-abc"),
        webhook_gid="1400000000001",
        webhook_secret=encrypt_api_key(WEBHOOK_SECRET_PLAIN),
        webhook_url_token=WEBHOOK_URL_TOKEN,
        is_active=True,
        status_sync_enabled=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def asana_integration_no_secret(db: Session, test_organization: Organization) -> AsanaIntegration:
    """Active AsanaIntegration with webhook_secret=None (handshake never completed)."""
    integration = AsanaIntegration(
        organization_id=test_organization.id,
        api_token=encrypt_api_key("asana-pat-abc"),
        webhook_gid="1400000000002",
        webhook_secret=None,
        webhook_url_token=WEBHOOK_URL_TOKEN_NO_SECRET,
        is_active=True,
        status_sync_enabled=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def asana_integration_never_enabled(db: Session, test_organization: Organization) -> AsanaIntegration:
    """Active AsanaIntegration that has never had /webhook/enable called --
    webhook_url_token is None, same as a freshly-connected integration.
    Defense-in-depth: no string token value should ever resolve this row."""
    integration = AsanaIntegration(
        organization_id=test_organization.id,
        api_token=encrypt_api_key("asana-pat-abc"),
        webhook_gid=None,
        webhook_secret=None,
        webhook_url_token=None,
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
    asana_task_gid="1300000000001",
    asana_completed=None,
    asana_status_category=None,
) -> FeedbackAsanaTask:
    link = FeedbackAsanaTask(
        organization_id=org_id,
        feedback_id=feedback_id,
        asana_task_gid=asana_task_gid,
        asana_task_url=f"https://app.asana.com/0/1/{asana_task_gid}",
        asana_task_name="Fix export crash",
        asana_completed=asana_completed,
        asana_status_category=asana_status_category,
        last_status_synced_at=datetime.utcnow() if asana_status_category else None,
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


def _inbound_url(token: str) -> str:
    return f"/api/v1/webhooks/asana/inbound/{token}"


# ============================================================================
# Phase 1 — Pure helper unit tests (no TestClient, no DB)
# ============================================================================

class TestVerifyAsanaSignature:
    def test_valid_signature_returns_true(self):
        from src.api.routes.asana_webhook import _verify_asana_signature

        body = b'{"events": []}'
        secret = "whsec_abc"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_asana_signature(body, sig, secret) is True

    def test_tampered_body_returns_false(self):
        from src.api.routes.asana_webhook import _verify_asana_signature

        body = b'{"events": []}'
        tampered = b'{"events": [1]}'
        secret = "whsec_abc"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert _verify_asana_signature(tampered, sig, secret) is False

    def test_empty_secret_returns_false_fail_closed(self):
        from src.api.routes.asana_webhook import _verify_asana_signature

        body = b'{"events": []}'
        sig = hmac.new(b"whsec_abc", body, hashlib.sha256).hexdigest()

        assert _verify_asana_signature(body, sig, "") is False

    def test_none_secret_returns_false_fail_closed(self):
        from src.api.routes.asana_webhook import _verify_asana_signature

        assert _verify_asana_signature(b"{}", "abc123", None) is False

    def test_missing_signature_returns_false(self):
        from src.api.routes.asana_webhook import _verify_asana_signature

        assert _verify_asana_signature(b"{}", "", "whsec_abc") is False

    def test_uses_hmac_compare_digest(self):
        from src.api.routes import asana_webhook

        body = b'{"events": []}'
        secret = "whsec_abc"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        with patch.object(asana_webhook.hmac, "compare_digest", wraps=asana_webhook.hmac.compare_digest) as mock_cmp:
            asana_webhook._verify_asana_signature(body, sig, secret)
            mock_cmp.assert_called_once()


# ============================================================================
# Phase 2 — Handshake branch
# ============================================================================

class TestAsanaWebhookHandshake:
    def test_first_handshake_persists_secret_and_echoes_header_no_reconcile(
        self, client: TestClient, asana_integration_no_secret: AsanaIntegration, db: Session
    ):
        feedback = _make_feedback(db, asana_integration_no_secret.organization_id)
        _make_link(db, asana_integration_no_secret.organization_id, feedback.id)

        response = client.post(
            _inbound_url(asana_integration_no_secret.webhook_url_token),
            content=b"{}",
            headers={"Content-Type": "application/json", "X-Hook-Secret": "brand-new-handshake-secret"},
        )
        assert response.status_code == 200
        assert response.headers["X-Hook-Secret"] == "brand-new-handshake-secret"

        db.refresh(asana_integration_no_secret)
        assert asana_integration_no_secret.webhook_secret is not None
        from src.utils.encryption import decrypt_api_key
        assert decrypt_api_key(asana_integration_no_secret.webhook_secret) == "brand-new-handshake-secret"

        # No reconcile happened -- no events written, workflow_status untouched.
        db.refresh(feedback)
        assert feedback.workflow_status == "in_review"
        assert _events_for(db, feedback.id) == []

    def test_attacker_rehandshake_on_org_with_existing_secret_401_and_secret_unchanged(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        """CRITICAL (sec review): an org that already completed its handshake
        must reject any further X-Hook-Secret request -- an attacker who
        discovers/guesses the webhook_url_token must NOT be able to
        overwrite a stored secret and forge later signed events."""
        original_encrypted_secret = asana_integration.webhook_secret

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=b"{}",
            headers={"Content-Type": "application/json", "X-Hook-Secret": "attacker-supplied-secret"},
        )
        assert response.status_code == 401

        db.refresh(asana_integration)
        assert asana_integration.webhook_secret == original_encrypted_secret
        from src.utils.encryption import decrypt_api_key
        assert decrypt_api_key(asana_integration.webhook_secret) == WEBHOOK_SECRET_PLAIN

    def test_rehandshake_after_enable_succeeds_but_bare_rehandshake_rejected(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        """A bare re-handshake against an org that already has a secret is
        rejected (401), secret unchanged. Only AFTER simulating
        POST /webhook/enable (which resets webhook_secret to None before
        registering a fresh Asana webhook) does a subsequent handshake
        succeed -- this is the only legitimate re-handshake path."""
        response1 = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=b"{}",
            headers={"Content-Type": "application/json", "X-Hook-Secret": "rotated-secret-1"},
        )
        assert response1.status_code == 401
        db.refresh(asana_integration)
        from src.utils.encryption import decrypt_api_key
        assert decrypt_api_key(asana_integration.webhook_secret) == WEBHOOK_SECRET_PLAIN

        # Simulate POST /webhook/enable: resets webhook_secret to None
        # ahead of registering a fresh webhook with Asana.
        asana_integration.webhook_secret = None
        db.commit()

        response2 = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=b"{}",
            headers={"Content-Type": "application/json", "X-Hook-Secret": "rotated-secret-2"},
        )
        assert response2.status_code == 200
        assert response2.headers["X-Hook-Secret"] == "rotated-secret-2"

        db.refresh(asana_integration)
        assert decrypt_api_key(asana_integration.webhook_secret) == "rotated-secret-2"

    def test_handshake_unknown_token_401(self, client: TestClient):
        response = client.post(
            _inbound_url("completely-unknown-token-xyz"),
            content=b"{}",
            headers={"Content-Type": "application/json", "X-Hook-Secret": "whatever"},
        )
        assert response.status_code == 401

    def test_handshake_unknown_token_for_never_enabled_is_401(
        self, client: TestClient, asana_integration_never_enabled: AsanaIntegration
    ):
        """A never-enabled integration's `webhook_url_token` column is
        genuinely NULL in the DB (the fixture). Posting a made-up token
        that matches no row must still 401 -- it must not accidentally
        resolve the NULL-token row (the query filters `.isnot(None)` in
        addition to equality, so a coincidental match against a NULL
        column can never happen), and no other row exists to match
        either."""
        response = client.post(
            _inbound_url("made-up-token-that-matches-no-row"),
            content=b"{}",
            headers={"Content-Type": "application/json", "X-Hook-Secret": "whatever"},
        )
        assert response.status_code == 401

    def test_handshake_missing_encryption_key_fails_closed_401(
        self, client: TestClient, asana_integration_no_secret: AsanaIntegration
    ):
        with patch.dict(os.environ, {}, clear=True):
            response = client.post(
                _inbound_url(asana_integration_no_secret.webhook_url_token),
                content=b"{}",
                headers={"Content-Type": "application/json", "X-Hook-Secret": "whatever"},
            )
        assert response.status_code == 401
        assert response.status_code != 500

    def test_handshake_response_never_leaks_stored_secret_of_other_org(
        self, client: TestClient, asana_integration: AsanaIntegration
    ):
        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=b"{}",
            headers={"Content-Type": "application/json", "X-Hook-Secret": "new-secret-value"},
        )
        assert WEBHOOK_SECRET_PLAIN not in response.text
        assert WEBHOOK_SECRET_PLAIN not in response.headers.get("X-Hook-Secret", "")


# ============================================================================
# Phase 2 — Signature enforcement (event branch)
# ============================================================================

class TestAsanaWebhookSignatureEnforcement:
    def test_missing_signature_header_401(self, client: TestClient, asana_integration: AsanaIntegration):
        payload = _completion_event_payload()
        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 401

    def test_bad_signature_401(self, client: TestClient, asana_integration: AsanaIntegration):
        payload = _completion_event_payload()
        body = json.dumps(payload).encode()
        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": "deadbeef"},
        )
        assert response.status_code == 401

    def test_tampered_body_rejected_401(self, client: TestClient, asana_integration: AsanaIntegration):
        body_a = json.dumps(_completion_event_payload(task_gid="1")).encode()
        body_b = json.dumps(_completion_event_payload(task_gid="2")).encode()
        sig_for_a = _make_asana_signature(body_a, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body_b,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig_for_a},
        )
        assert response.status_code == 401

    def test_no_secret_configured_rejected_401_fail_closed(
        self, client: TestClient, asana_integration_no_secret: AsanaIntegration
    ):
        payload = _completion_event_payload()
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, "whatever-guessed-secret")

        response = client.post(
            _inbound_url(asana_integration_no_secret.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 401

    def test_unknown_token_401(self, client: TestClient):
        payload = _completion_event_payload()
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, "whatever-guessed-secret")

        response = client.post(
            _inbound_url("completely-unknown-token-xyz"),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 401

    def test_never_500s_on_corrupt_encrypted_secret(self, client: TestClient, asana_integration: AsanaIntegration):
        payload = _completion_event_payload()
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        with patch(
            "src.api.routes.asana_webhook.decrypt_api_key",
            side_effect=Exception("InvalidToken"),
        ):
            response = client.post(
                _inbound_url(asana_integration.webhook_url_token),
                content=body,
                headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
            )
        assert response.status_code == 401

    def test_response_never_leaks_secret(self, client: TestClient, asana_integration: AsanaIntegration, db: Session):
        feedback = _make_feedback(db, asana_integration.organization_id)
        _make_link(db, asana_integration.organization_id, feedback.id, asana_status_category="new")

        payload = _completion_event_payload()
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert WEBHOOK_SECRET_PLAIN not in response.text
        assert sig not in response.text

    def test_invalid_json_returns_400(self, client: TestClient, asana_integration: AsanaIntegration):
        body = b"not-json-at-all{{{"
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)
        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 400

    def test_non_dict_json_returns_400(self, client: TestClient, asana_integration: AsanaIntegration):
        body = b"[1, 2, 3]"
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)
        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 400


# ============================================================================
# Phase 3 — Event discrimination (non-completion / non-task events are 200 no-ops)
# ============================================================================

class TestAsanaWebhookEventDiscrimination:
    def test_no_events_key_is_200_noop(self, client: TestClient, asana_integration: AsanaIntegration):
        body = json.dumps({"events": []}).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)
        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_non_task_resource_event_is_200_noop(self, client: TestClient, asana_integration: AsanaIntegration):
        payload = {
            "events": [
                {"resource": {"gid": "123", "resource_type": "project"}, "action": "changed"}
            ]
        }
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)
        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


# ============================================================================
# Phase 4 — Completion-change reconcile
# ============================================================================

class TestAsanaWebhookCompletionChange:
    def test_verified_completion_event_moves_feedback_one_event(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        feedback = _make_feedback(db, asana_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            asana_integration.organization_id,
            feedback.id,
            asana_task_gid="1300000000001",
            asana_completed=False,
            asana_status_category="new",
        )

        payload = _completion_event_payload(task_gid="1300000000001", completed=True)
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        events = _events_for(db, feedback.id)
        assert len(events) == 1
        assert events[0].event_type == "status_changed"
        assert events[0].old_value == "new"
        assert events[0].new_value == "resolved"
        assert events[0].metadata_["source"] == "asana"
        assert events[0].metadata_["asana_task_gid"] == "1300000000001"
        assert events[0].metadata_["asana_completed"] is True

    def test_completed_value_fetched_via_client_when_absent_from_payload(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        feedback = _make_feedback(db, asana_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            asana_integration.organization_id,
            feedback.id,
            asana_task_gid="1300000000001",
            asana_completed=False,
            asana_status_category="new",
        )

        # A non-completion field change carries no `change.new_value` for
        # `completed` -- receiver must fall back to AsanaClient.get_task.
        payload = _non_completion_event_payload(task_gid="1300000000001")
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        mock_client = MagicMock()
        mock_client.get_task.return_value = {"completed": True, "completed_at": None, "memberships": []}
        with patch("src.api.routes.asana_webhook.AsanaClient", return_value=mock_client):
            response = client.post(
                _inbound_url(asana_integration.webhook_url_token),
                content=body,
                headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
            )
        assert response.status_code == 200
        mock_client.get_task.assert_called_once_with("1300000000001")

        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"
        assert len(_events_for(db, feedback.id)) == 1

    def test_status_sync_disabled_acks_200_no_change_no_event(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        asana_integration.status_sync_enabled = False
        db.commit()
        feedback = _make_feedback(db, asana_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            asana_integration.organization_id,
            feedback.id,
            asana_task_gid="1300000000001",
            asana_completed=False,
            asana_status_category="new",
        )

        payload = _completion_event_payload(task_gid="1300000000001", completed=True)
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "new"
        assert _events_for(db, feedback.id) == []

    def test_first_observation_via_webhook_seeds_no_apply(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        feedback = _make_feedback(db, asana_integration.organization_id, workflow_status="new")
        _make_link(db, asana_integration.organization_id, feedback.id, asana_task_gid="1300000000001")

        payload = _completion_event_payload(task_gid="1300000000001", completed=True)
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "new"
        assert _events_for(db, feedback.id) == []

        link = (
            db.query(FeedbackAsanaTask)
            .filter(FeedbackAsanaTask.feedback_id == feedback.id)
            .first()
        )
        assert link.asana_status_category == "done"

    def test_unlinked_task_is_200_noop(self, client: TestClient, asana_integration: AsanaIntegration, db: Session):
        payload = _completion_event_payload(task_gid="9999999999999", completed=True)
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200
        assert db.query(FeedbackWorkflowEvent).count() == 0

    def test_idempotency_two_deliveries_same_change_single_event(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        """Webhook redelivered on the SAME change must result in exactly one
        status_changed event total -- the second reconcile sees fetched ==
        already-stored category -> noop (race guard / idempotency window)."""
        feedback = _make_feedback(db, asana_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            asana_integration.organization_id,
            feedback.id,
            asana_task_gid="1300000000001",
            asana_completed=False,
            asana_status_category="new",
        )

        payload = _completion_event_payload(task_gid="1300000000001", completed=True)
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)
        headers = {"Content-Type": "application/json", "X-Hook-Signature": sig}

        response1 = client.post(_inbound_url(asana_integration.webhook_url_token), content=body, headers=headers)
        response2 = client.post(_inbound_url(asana_integration.webhook_url_token), content=body, headers=headers)

        assert response1.status_code == 200
        assert response2.status_code == 200
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"
        assert len(_events_for(db, feedback.id)) == 1

    def test_multi_task_feedback_most_advanced_category_wins(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        """A feedback item linked to two Asana tasks: one moves to 'done',
        the other stays 'new' -- most_advanced picks 'done'."""
        feedback = _make_feedback(db, asana_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            asana_integration.organization_id,
            feedback.id,
            asana_task_gid="1300000000001",
            asana_completed=False,
            asana_status_category="new",
        )
        _make_link(
            db,
            asana_integration.organization_id,
            feedback.id,
            asana_task_gid="1300000000002",
            asana_completed=False,
            asana_status_category="new",
        )

        payload = _completion_event_payload(task_gid="1300000000001", completed=True)
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"
        assert len(_events_for(db, feedback.id)) == 1

    def test_custom_status_mapping_is_honored(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        asana_integration.status_mapping = {"done": "closed"}
        db.commit()

        feedback = _make_feedback(db, asana_integration.organization_id, workflow_status="new")
        _make_link(
            db,
            asana_integration.organization_id,
            feedback.id,
            asana_task_gid="1300000000001",
            asana_completed=False,
            asana_status_category="new",
        )

        payload = _completion_event_payload(task_gid="1300000000001", completed=True)
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "closed"

    def test_reopen_task_moves_status_back_when_mapped(
        self, client: TestClient, asana_integration: AsanaIntegration, db: Session
    ):
        feedback = _make_feedback(db, asana_integration.organization_id, workflow_status="resolved")
        _make_link(
            db,
            asana_integration.organization_id,
            feedback.id,
            asana_task_gid="1300000000001",
            asana_completed=True,
            asana_status_category="done",
        )

        payload = _completion_event_payload(task_gid="1300000000001", completed=False)
        body = json.dumps(payload).encode()
        sig = _make_asana_signature(body, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            _inbound_url(asana_integration.webhook_url_token),
            content=body,
            headers={"Content-Type": "application/json", "X-Hook-Signature": sig},
        )
        assert response.status_code == 200

        db.refresh(feedback)
        assert feedback.workflow_status == "new"
        assert len(_events_for(db, feedback.id)) == 1
