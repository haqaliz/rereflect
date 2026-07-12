"""
TDD tests for the Zendesk webhook entry point (ingestion-webhook aspect).

Covers: POST /api/v1/webhooks/zendesk/events. Mirrors TestIntercomWebhook in
test_intercom.py; seeds ZendeskIntegration + FeedbackSource rows directly
(not via the connect API), per the plan.

# Acceptance-criteria traceability (Phase 5):
# AC1 (valid signature + new-ticket -> 200 + queued, correct subdomain)
#   -> TestZendeskWebhookQueueing.test_webhook_valid_signature_new_ticket_queues_event
# AC2 (invalid/missing signature -> 401, nothing queued)
#   -> TestZendeskSignatureEnforcement.test_webhook_rejects_missing_signature_header
#   -> TestZendeskSignatureEnforcement.test_webhook_rejects_missing_timestamp_header
#   -> TestZendeskSignatureEnforcement.test_webhook_rejects_invalid_signature
#   -> TestZendeskSignatureEnforcement.test_webhook_rejects_tampered_body
# AC3 (unknown subdomain / no active zendesk source -> 200 no-op, nothing created)
#   -> TestZendeskRouteSkeleton.test_webhook_ignores_unknown_subdomain
#   -> TestZendeskWebhookQueueing.test_webhook_no_active_source_is_noop
# AC4 (already ingested via pull -> deduped, no duplicate)
#   -> TestZendeskWebhookQueueing.test_webhook_dedupes_ticket_already_ingested_via_pull
"""
import base64
import hashlib
import hmac
import json
import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.zendesk_integration import ZendeskIntegration
from src.models.feedback import FeedbackItem
from src.models.feedback_source import FeedbackSource
from src.models.feedback_source_event import FeedbackSourceEvent
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.feedback_zendesk_sync import FeedbackZendeskSync
from src.utils.encryption import encrypt_api_key


# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

SUBDOMAIN = "acmeco"
WEBHOOK_SECRET_PLAIN = "whsec_test_123"


def _make_zendesk_signature(body: bytes, timestamp: str, secret: str) -> str:
    """Helper to compute the Zendesk HMAC-SHA256 signature (base64-encoded)."""
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _valid_ticket_payload(ticket_id=35436, subdomain=SUBDOMAIN):
    return {
        "subdomain": subdomain,
        "ticket": {
            "id": ticket_id,
            "subject": "Can't log in",
            "description": "I get an error when I try to log in.",
            "status": "new",
            "requester_email": "jane@customer.example.com",
            "tags": ["login"],
        },
    }


# Anti-spoof discriminator (webhook-realtime aspect, design task #3): the
# operator's Zendesk UPDATE-trigger body must set this exact field/value so
# the status-change branch can never be reached via the ingestion trigger's
# (or an attacker's) payload shape. See docs/SELF_HOSTING.md.
STATUS_CHANGE_EVENT = "ticket.status_changed"


def _status_change_payload(ticket_id=35436, status="solved", subdomain=SUBDOMAIN):
    return {
        "event": STATUS_CHANGE_EVENT,
        "subdomain": subdomain,
        "ticket": {
            "id": ticket_id,
            "status": status,
        },
    }


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def _fernet_key_env():
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        yield


@pytest.fixture
def zendesk_integration(db: Session, test_organization: Organization) -> ZendeskIntegration:
    """Directly-seeded active ZendeskIntegration with a known decrypted webhook_secret."""
    integration = ZendeskIntegration(
        organization_id=test_organization.id,
        subdomain=SUBDOMAIN,
        email="operator@acmeco.com",
        api_token=encrypt_api_key("zendesk-api-token-abc"),
        webhook_secret=encrypt_api_key(WEBHOOK_SECRET_PLAIN),
        is_active=True,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def zendesk_integration_no_secret(db: Session, test_organization: Organization) -> ZendeskIntegration:
    """Active ZendeskIntegration with webhook_secret=None (BYOK-only connect)."""
    integration = ZendeskIntegration(
        organization_id=test_organization.id,
        subdomain=SUBDOMAIN,
        email="operator@acmeco.com",
        api_token=encrypt_api_key("zendesk-api-token-abc"),
        webhook_secret=None,
        is_active=True,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def zendesk_source(db: Session, test_organization: Organization) -> FeedbackSource:
    """Directly-seeded active zendesk FeedbackSource (simulates backend-connection auto-provision)."""
    source = FeedbackSource(
        organization_id=test_organization.id,
        source_type="zendesk",
        name="Zendesk",
        is_active=True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


# ============================================================================
# Phase 1 — Pure helper unit tests (no TestClient, no DB)
# ============================================================================

class TestResolveZendeskSubdomain:
    """Tests for _resolve_zendesk_subdomain (framework-free)."""

    def test_returns_subdomain_from_payload(self):
        from src.api.routes.source_webhooks import _resolve_zendesk_subdomain

        result = _resolve_zendesk_subdomain({"subdomain": "acmeco"}, {})
        assert result == "acmeco"

    def test_lowercases_payload_subdomain(self):
        from src.api.routes.source_webhooks import _resolve_zendesk_subdomain

        result = _resolve_zendesk_subdomain({"subdomain": "ACMECO"}, {})
        assert result == "acmeco"

    def test_falls_back_to_ticket_url_host(self):
        from src.api.routes.source_webhooks import _resolve_zendesk_subdomain

        payload = {"ticket": {"url": "https://acmeco.zendesk.com/api/v2/tickets/1.json"}}
        result = _resolve_zendesk_subdomain(payload, {})
        assert result == "acmeco"

    def test_falls_back_to_header(self):
        from src.api.routes.source_webhooks import _resolve_zendesk_subdomain

        result = _resolve_zendesk_subdomain({}, {"X-Zendesk-Subdomain": "acmeco"})
        assert result == "acmeco"

    def test_header_case_insensitive_normalized(self):
        from src.api.routes.source_webhooks import _resolve_zendesk_subdomain

        result = _resolve_zendesk_subdomain({}, {"X-Zendesk-Subdomain": "ACMECO"})
        assert result == "acmeco"

    def test_returns_none_when_unresolvable(self):
        from src.api.routes.source_webhooks import _resolve_zendesk_subdomain

        result = _resolve_zendesk_subdomain({}, {})
        assert result is None

    def test_returns_none_for_malformed_ticket_url(self):
        from src.api.routes.source_webhooks import _resolve_zendesk_subdomain

        payload = {"ticket": {"url": "not-a-url"}}
        result = _resolve_zendesk_subdomain(payload, {})
        assert result is None

    def test_payload_subdomain_takes_precedence_over_url_and_header(self):
        from src.api.routes.source_webhooks import _resolve_zendesk_subdomain

        payload = {
            "subdomain": "primary",
            "ticket": {"url": "https://secondary.zendesk.com/tickets/1.json"},
        }
        result = _resolve_zendesk_subdomain(payload, {"X-Zendesk-Subdomain": "tertiary"})
        assert result == "primary"


class TestVerifyZendeskSignature:
    """Tests for _verify_zendesk_signature (framework-free)."""

    def test_valid_signature_returns_true(self):
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        timestamp = "2026-07-05T00:00:00Z"
        secret = "whsec_abc"
        signature = base64.b64encode(
            hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
        ).decode()

        assert _verify_zendesk_signature(body, timestamp, signature, secret) is True

    def test_tampered_body_returns_false(self):
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        tampered_body = b'{"ticket": {"id": 2}}'
        timestamp = "2026-07-05T00:00:00Z"
        secret = "whsec_abc"
        signature = base64.b64encode(
            hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
        ).decode()

        assert _verify_zendesk_signature(tampered_body, timestamp, signature, secret) is False

    def test_tampered_timestamp_returns_false(self):
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        timestamp = "2026-07-05T00:00:00Z"
        wrong_timestamp = "2026-07-05T00:00:01Z"
        secret = "whsec_abc"
        signature = base64.b64encode(
            hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
        ).decode()

        assert _verify_zendesk_signature(body, wrong_timestamp, signature, secret) is False

    def test_empty_secret_returns_false_fail_closed(self):
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        timestamp = "2026-07-05T00:00:00Z"
        signature = base64.b64encode(
            hmac.new(b"whsec_abc", timestamp.encode() + body, hashlib.sha256).digest()
        ).decode()

        assert _verify_zendesk_signature(body, timestamp, signature, "") is False

    def test_none_secret_returns_false_fail_closed(self):
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        timestamp = "2026-07-05T00:00:00Z"
        signature = "irrelevant"

        assert _verify_zendesk_signature(body, timestamp, signature, None) is False

    def test_uses_hmac_compare_digest(self):
        from src.api.routes import source_webhooks

        body = b'{"ticket": {"id": 1}}'
        timestamp = "2026-07-05T00:00:00Z"
        secret = "whsec_abc"
        signature = base64.b64encode(
            hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
        ).decode()

        with patch.object(source_webhooks.hmac, "compare_digest", wraps=source_webhooks.hmac.compare_digest) as mock_cmp:
            source_webhooks._verify_zendesk_signature(body, timestamp, signature, secret)
            mock_cmp.assert_called_once()


# ============================================================================
# Phase 2 — Route skeleton: raw body, JSON parse, subdomain/integration resolution
# ============================================================================

class TestZendeskRouteSkeleton:
    """Tests for POST /api/v1/webhooks/zendesk/events (pre-signature phase)."""

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_ignores_missing_subdomain(self, mock_queue, client: TestClient):
        payload = {"ticket": {"id": 1, "subject": "no subdomain here"}}
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ignored", "reason": "missing_subdomain"}
        mock_queue.assert_not_called()

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_ignores_unknown_subdomain(self, mock_queue, client: TestClient, db: Session):
        payload = _valid_ticket_payload(subdomain="nosuchorg")
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ignored", "reason": "unknown_subdomain"}
        mock_queue.assert_not_called()

    def test_webhook_rejects_invalid_json(self, client: TestClient):
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=b"not-json-at-all{{{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400


# ============================================================================
# Phase 3 — Signature enforcement
# ============================================================================

class TestZendeskSignatureEnforcement:
    """Tests for HMAC signature enforcement once an integration is resolved."""

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_rejects_missing_signature_header(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload = _valid_ticket_payload()
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature-Timestamp": "2026-07-05T00:00:00Z",
            },
        )
        assert response.status_code == 401
        mock_queue.assert_not_called()

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_rejects_missing_timestamp_header(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload = _valid_ticket_payload()
        body = json.dumps(payload).encode()
        sig = _make_zendesk_signature(body, "2026-07-05T00:00:00Z", WEBHOOK_SECRET_PLAIN)
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
            },
        )
        assert response.status_code == 401
        mock_queue.assert_not_called()

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_rejects_invalid_signature(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload = _valid_ticket_payload()
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        wrong_sig = _make_zendesk_signature(body, timestamp, "wrong-secret")
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": wrong_sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 401
        mock_queue.assert_not_called()

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_rejects_tampered_body(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload_a = _valid_ticket_payload(ticket_id=1)
        payload_b = _valid_ticket_payload(ticket_id=2)
        body_a = json.dumps(payload_a).encode()
        body_b = json.dumps(payload_b).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig_for_a = _make_zendesk_signature(body_a, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body_b,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig_for_a,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 401
        mock_queue.assert_not_called()

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_rejects_when_webhook_secret_not_set(
        self, mock_queue, client: TestClient, zendesk_integration_no_secret, zendesk_source
    ):
        payload = _valid_ticket_payload()
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        # Sign with some plausible secret -- doesn't matter, secret is None server-side.
        sig = _make_zendesk_signature(body, timestamp, "whatever")
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 401
        assert response.json() != {"status": "ignored", "reason": "unknown_subdomain"}
        assert response.json() != {"status": "ignored", "reason": "no_active_source"}
        mock_queue.assert_not_called()

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_never_500s_on_corrupt_encrypted_secret(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload = _valid_ticket_payload()
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        with patch(
            "src.api.routes.source_webhooks.decrypt_api_key",
            side_effect=Exception("InvalidToken"),
        ):
            response = client.post(
                "/api/v1/webhooks/zendesk/events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Zendesk-Webhook-Signature": sig,
                    "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
                },
            )
        assert response.status_code == 401
        mock_queue.assert_not_called()


# ============================================================================
# Phase 4 — Active-source lookup, dedup pre-check, queue
# ============================================================================

class TestZendeskWebhookQueueing:
    """Tests for the success path and its edge cases."""

    @patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-zd-1")
    def test_webhook_valid_signature_new_ticket_queues_event(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload = _valid_ticket_payload(ticket_id=35436)
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        mock_queue.assert_called_once_with(
            source_type="zendesk",
            external_event_id="35436",
            event_type="ticket.created",
            event_data={"ticket": payload["ticket"], "subdomain": SUBDOMAIN},
            provider_context={"subdomain": SUBDOMAIN},
        )

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_no_active_source_is_noop(
        self, mock_queue, client: TestClient, zendesk_integration, db: Session
    ):
        payload = _valid_ticket_payload()
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ignored", "reason": "no_active_source"}
        mock_queue.assert_not_called()
        assert db.query(FeedbackSourceEvent).count() == 0

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_dedupes_ticket_already_ingested_via_pull(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source, db: Session
    ):
        existing = FeedbackSourceEvent(
            source_id=zendesk_source.id,
            organization_id=zendesk_source.organization_id,
            external_event_id="35436",
            event_type="ticket.created",
            status="processed",
        )
        db.add(existing)
        db.commit()

        payload = _valid_ticket_payload(ticket_id=35436)
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "duplicate"}
        mock_queue.assert_not_called()
        assert db.query(FeedbackSourceEvent).filter(
            FeedbackSourceEvent.external_event_id == "35436"
        ).count() == 1

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_does_not_dedupe_against_ignored_or_failed_rows(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source, db: Session
    ):
        """
        A prior "ignored"/"failed" FeedbackSourceEvent row for the same
        ticket_id must not permanently short-circuit a later legitimate
        delivery of that same ticket (e.g. the first delivery was ignored
        for an unrelated reason -- empty text, trigger mismatch -- and a
        redelivery or re-sync should still get a chance to be processed).
        """
        existing = FeedbackSourceEvent(
            source_id=zendesk_source.id,
            organization_id=zendesk_source.organization_id,
            external_event_id="35436",
            event_type="ticket.created",
            status="ignored",
        )
        db.add(existing)
        db.commit()

        payload = _valid_ticket_payload(ticket_id=35436)
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        mock_queue.assert_called_once()

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_webhook_missing_ticket_id_is_noop(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload = {"subdomain": SUBDOMAIN, "ticket": {"subject": "no id field"}}
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ignored", "reason": "missing_ticket_id"}
        mock_queue.assert_not_called()

    @patch("src.api.routes.source_webhooks.queue_source_event", side_effect=Exception("broker down"))
    def test_webhook_broker_failure_returns_500(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload = _valid_ticket_payload()
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )
        assert response.status_code == 500


# ============================================================================
# Phase 5 — never-500 sweep
# ============================================================================

class TestZendeskWebhookNever500s:
    """Property-style sweep: every response class is 200, 401, or 400 (except the
    deliberate broker-failure 500 path covered above)."""

    @pytest.mark.parametrize(
        "body,headers",
        [
            (b"", {}),
            (b"{}", {}),
            (b"not json", {}),
            (b"\x00\x01\x02garbage", {}),
            (json.dumps({"subdomain": "acmeco"}).encode(), {}),
            (json.dumps(_valid_ticket_payload()).encode(), {"X-Zendesk-Webhook-Signature": "bogus"}),
            (
                json.dumps(_valid_ticket_payload()).encode(),
                {"X-Zendesk-Webhook-Signature-Timestamp": "2026-07-05T00:00:00Z"},
            ),
        ],
    )
    def test_malformed_inputs_never_500(self, client: TestClient, body, headers):
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={"Content-Type": "application/json", **headers},
        )
        assert response.status_code in (200, 400, 401)

    @pytest.mark.parametrize(
        "body",
        [
            b"[]",
            b"123",
            b'"x"',
            b"true",
            b"null",
        ],
    )
    def test_valid_non_dict_json_returns_400_not_500(self, client: TestClient, body):
        """Valid JSON that isn't an object (list/number/string/bool/null) must be
        rejected with 400, not crash with a 500 when `_resolve_zendesk_subdomain`
        calls `.get(...)` on a non-dict payload."""
        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_response_never_leaks_secret_or_signature(
        self, client: TestClient, zendesk_integration, zendesk_source
    ):
        payload = _valid_ticket_payload()
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        with patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-1"):
            response = client.post(
                "/api/v1/webhooks/zendesk/events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Zendesk-Webhook-Signature": sig,
                    "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
                },
            )
        assert WEBHOOK_SECRET_PLAIN not in response.text
        assert sig not in response.text


# ============================================================================
# Phase 6 (webhook-realtime aspect) — status-change branch
#
# Discriminator (anti-spoof, design task #3): payload["event"] ==
# "ticket.status_changed" (see STATUS_CHANGE_EVENT / _status_change_payload
# above). This field is NOT present in the ingestion trigger's payload
# shape, so an ingestion delivery can never accidentally (or maliciously)
# reach the status-change branch, and vice versa.
# ============================================================================


def _make_linked_feedback(
    db: Session, org_id: int, ticket_id, workflow_status="in_review"
) -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=org_id,
        text="It crashes on export",
        source="zendesk",
        source_external_id=str(ticket_id),
        workflow_status=workflow_status,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def _make_sidecar(db: Session, feedback_id: int, last_ticket_status: str) -> FeedbackZendeskSync:
    from datetime import datetime

    row = FeedbackZendeskSync(
        feedback_id=feedback_id,
        last_ticket_status=last_ticket_status,
        last_status_synced_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _events_for(db: Session, feedback_id: int):
    return (
        db.query(FeedbackWorkflowEvent)
        .filter(FeedbackWorkflowEvent.feedback_id == feedback_id)
        .all()
    )


class TestZendeskStatusChangeWebhook:
    """Tests for the status-change branch of POST /api/v1/webhooks/zendesk/events."""

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_verified_status_event_sync_on_resolves_feedback_one_event(
        self, mock_queue, client: TestClient, zendesk_integration, db: Session
    ):
        zendesk_integration.status_sync_enabled = True
        db.commit()
        feedback = _make_linked_feedback(db, zendesk_integration.organization_id, 35436, workflow_status="in_review")
        _make_sidecar(db, feedback.id, "open")

        payload = _status_change_payload(ticket_id=35436, status="solved")
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )

        assert response.status_code == 200
        mock_queue.assert_not_called()

        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"

        events = _events_for(db, feedback.id)
        assert len(events) == 1
        assert events[0].event_type == "status_changed"
        assert events[0].old_value == "in_review"
        assert events[0].new_value == "resolved"
        assert events[0].metadata_["source"] == "zendesk"
        assert events[0].metadata_["zendesk_status"] == "solved"
        assert events[0].metadata_["zendesk_ticket_id"] == "35436"

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar.last_ticket_status == "solved"

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_sync_disabled_acks_200_no_change_no_event(
        self, mock_queue, client: TestClient, zendesk_integration, db: Session
    ):
        zendesk_integration.status_sync_enabled = False
        db.commit()
        feedback = _make_linked_feedback(db, zendesk_integration.organization_id, 35436, workflow_status="in_review")
        _make_sidecar(db, feedback.id, "open")

        payload = _status_change_payload(ticket_id=35436, status="solved")
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )

        assert response.status_code == 200
        mock_queue.assert_not_called()

        db.refresh(feedback)
        assert feedback.workflow_status == "in_review"
        assert _events_for(db, feedback.id) == []

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar.last_ticket_status == "open"

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_first_observation_via_webhook_seeds_no_apply(
        self, mock_queue, client: TestClient, zendesk_integration, db: Session
    ):
        zendesk_integration.status_sync_enabled = True
        db.commit()
        feedback = _make_linked_feedback(db, zendesk_integration.organization_id, 35436, workflow_status="new")

        payload = _status_change_payload(ticket_id=35436, status="open")
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )

        assert response.status_code == 200
        mock_queue.assert_not_called()

        db.refresh(feedback)
        assert feedback.workflow_status == "new"
        assert _events_for(db, feedback.id) == []

        sidecar = db.get(FeedbackZendeskSync, feedback.id)
        assert sidecar is not None
        assert sidecar.last_ticket_status == "open"

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_unlinked_ticket_is_200_noop(
        self, mock_queue, client: TestClient, zendesk_integration, db: Session
    ):
        zendesk_integration.status_sync_enabled = True
        db.commit()

        payload = _status_change_payload(ticket_id=99999, status="solved")
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )

        assert response.status_code == 200
        mock_queue.assert_not_called()
        assert db.query(FeedbackWorkflowEvent).count() == 0
        assert db.query(FeedbackZendeskSync).count() == 0

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_bad_signature_rejected_401_status_branch(
        self, mock_queue, client: TestClient, zendesk_integration, db: Session
    ):
        zendesk_integration.status_sync_enabled = True
        db.commit()
        feedback = _make_linked_feedback(db, zendesk_integration.organization_id, 35436, workflow_status="in_review")
        _make_sidecar(db, feedback.id, "open")

        payload = _status_change_payload(ticket_id=35436, status="solved")
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        wrong_sig = _make_zendesk_signature(body, timestamp, "wrong-secret")

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": wrong_sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )

        assert response.status_code == 401
        mock_queue.assert_not_called()
        db.refresh(feedback)
        assert feedback.workflow_status == "in_review"
        assert _events_for(db, feedback.id) == []

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_missing_hmac_rejected_401_status_branch(
        self, mock_queue, client: TestClient, zendesk_integration, db: Session
    ):
        zendesk_integration.status_sync_enabled = True
        db.commit()
        payload = _status_change_payload(ticket_id=35436, status="solved")
        body = json.dumps(payload).encode()

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 401
        mock_queue.assert_not_called()

    @patch("src.api.routes.source_webhooks.queue_source_event")
    def test_idempotency_two_reconciles_same_change_single_event(
        self, mock_queue, client: TestClient, zendesk_integration, db: Session
    ):
        """Webhook redelivered (or webhook + poll) on the SAME change must
        result in exactly one status_changed event total -- the second
        reconcile sees fetched == already-stored status -> noop
        (change-gate closes the idempotency window)."""
        zendesk_integration.status_sync_enabled = True
        db.commit()
        feedback = _make_linked_feedback(db, zendesk_integration.organization_id, 35436, workflow_status="in_review")
        _make_sidecar(db, feedback.id, "open")

        payload = _status_change_payload(ticket_id=35436, status="solved")
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)
        headers = {
            "Content-Type": "application/json",
            "X-Zendesk-Webhook-Signature": sig,
            "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
        }

        response1 = client.post("/api/v1/webhooks/zendesk/events", content=body, headers=headers)
        response2 = client.post("/api/v1/webhooks/zendesk/events", content=body, headers=headers)

        assert response1.status_code == 200
        assert response2.status_code == 200
        db.refresh(feedback)
        assert feedback.workflow_status == "resolved"
        assert len(_events_for(db, feedback.id)) == 1

    @patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-zd-ingest")
    def test_ingestion_ticket_created_path_unchanged_characterization(
        self, mock_queue, client: TestClient, zendesk_integration, zendesk_source, db: Session
    ):
        """Characterization: a normal ingestion payload (no `event` field --
        the discriminator is absent, exactly as today's operator-configured
        creation trigger sends it) must still queue via the untouched
        ticket.created path, byte-identical to the pre-existing behavior."""
        payload = _valid_ticket_payload(ticket_id=77777)
        body = json.dumps(payload).encode()
        timestamp = "2026-07-05T00:00:00Z"
        sig = _make_zendesk_signature(body, timestamp, WEBHOOK_SECRET_PLAIN)

        response = client.post(
            "/api/v1/webhooks/zendesk/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Zendesk-Webhook-Signature": sig,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        mock_queue.assert_called_once_with(
            source_type="zendesk",
            external_event_id="77777",
            event_type="ticket.created",
            event_data={"ticket": payload["ticket"], "subdomain": SUBDOMAIN},
            provider_context={"subdomain": SUBDOMAIN},
        )
