"""Tests for inbound email webhook endpoint (Resend inbound)."""
import json
import hashlib
import hmac
import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback_source import FeedbackSource
from src.models.feedback import FeedbackItem
from src.api.auth import hash_password, create_access_token


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def email_source(db: Session, test_organization: Organization) -> FeedbackSource:
    """Create an active email feedback source with a known inbound address."""
    source = FeedbackSource(
        organization_id=test_organization.id,
        source_type="email",
        name="Test Email Source",
        provider_config={"inbound_address": "feedback-abc12345@rereflect.ca"},
        is_active=True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@pytest.fixture
def inactive_email_source(db: Session, test_organization: Organization) -> FeedbackSource:
    """Create an inactive email feedback source."""
    source = FeedbackSource(
        organization_id=test_organization.id,
        source_type="email",
        name="Inactive Email Source",
        provider_config={"inbound_address": "feedback-inactive1@rereflect.ca"},
        is_active=False,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _make_inbound_payload(
    to: str = "feedback-abc12345@rereflect.ca",
    from_addr: str = "customer@example.com",
    subject: str = "Product issue",
    text: str = "The dashboard is slow.",
    html: str = None,
    message_id: str = "<msg-001@mail.example.com>",
) -> dict:
    """Build a Resend inbound email webhook payload (matches real Resend format)."""
    data = {
        "from": from_addr,
        "to": [to],
        "subject": subject,
        "text": text,
        "message_id": message_id,
    }
    if html:
        data["html"] = html
    return {"created_at": "2026-01-01T00:00:00.000Z", "data": data}


# ============================================================================
# Valid Inbound Tests
# ============================================================================

class TestEmailInboundWebhook:
    """Tests for POST /api/v1/webhooks/email/inbound."""

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    @patch("src.api.routes.email_webhooks.queue_source_event", return_value="task-email-001")
    def test_valid_inbound_creates_feedback(
        self,
        mock_queue: MagicMock,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
        email_source: FeedbackSource,
    ):
        """Valid email should be processed and queued for analysis."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.get.return_value = None  # no dedup hit
        mock_redis_instance.incr.return_value = 1  # rate limit count
        mock_redis.return_value = mock_redis_instance

        payload = _make_inbound_payload()
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        mock_queue.assert_called_once()

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    @patch("src.api.routes.email_webhooks.queue_source_event", return_value="task-email-002")
    def test_html_email_is_parsed(
        self,
        mock_queue: MagicMock,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
        email_source: FeedbackSource,
    ):
        """HTML email bodies should be converted to plain text for analysis."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.get.return_value = None
        mock_redis_instance.incr.return_value = 1
        mock_redis.return_value = mock_redis_instance

        payload = _make_inbound_payload(
            html="<p>The <b>dashboard</b> loads slowly.</p>",
            text="The dashboard loads slowly.",
            message_id="<msg-html@mail.example.com>",
        )
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"


# ============================================================================
# Validation Tests
# ============================================================================

class TestEmailInboundValidation:
    """Tests for input validation on the webhook."""

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    def test_missing_recipient_returns_400(
        self,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
    ):
        """Should return 400 when 'to' field is missing."""
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        payload = {
            "created_at": "2026-01-01T00:00:00.000Z",
            "data": {
                "from": "customer@example.com",
                "subject": "Test",
                "text": "Test body",
                "message_id": "<msg@test.com>",
            },
        }
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 400

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    def test_unknown_recipient_returns_400(
        self,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
    ):
        """Should return 400 when recipient address is not found in any source."""
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        payload = _make_inbound_payload(to="feedback-nonexistent@rereflect.ca")
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 400

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    def test_inactive_source_rejected(
        self,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
        inactive_email_source: FeedbackSource,
    ):
        """Should reject emails to an inactive source."""
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        payload = _make_inbound_payload(to="feedback-inactive1@rereflect.ca")
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 400


# ============================================================================
# Rate Limiting Tests
# ============================================================================

class TestEmailRateLimiting:
    """Tests for rate limiting (100 emails/hr/org)."""

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    def test_rate_limited_returns_429(
        self,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
        email_source: FeedbackSource,
    ):
        """Should return 429 when rate limit is exceeded."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.get.return_value = None  # no dedup
        mock_redis_instance.incr.return_value = 101  # over limit
        mock_redis.return_value = mock_redis_instance

        payload = _make_inbound_payload()
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 429

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    @patch("src.api.routes.email_webhooks.queue_source_event", return_value="task-ok")
    def test_under_rate_limit_passes(
        self,
        mock_queue: MagicMock,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
        email_source: FeedbackSource,
    ):
        """Should pass when under the rate limit."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.get.return_value = None  # no dedup
        mock_redis_instance.incr.return_value = 50  # under limit
        mock_redis.return_value = mock_redis_instance

        payload = _make_inbound_payload(message_id="<unique-msg@test.com>")
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 200


# ============================================================================
# Duplicate Detection Tests
# ============================================================================

class TestEmailDeduplication:
    """Tests for Message-ID based deduplication."""

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    def test_duplicate_message_id_skipped(
        self,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
        email_source: FeedbackSource,
    ):
        """Should skip processing if Message-ID was already seen."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.get.return_value = b"1"  # dedup hit
        mock_redis.return_value = mock_redis_instance

        payload = _make_inbound_payload(message_id="<already-seen@mail.com>")
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "duplicate"

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=True)
    @patch("src.api.routes.email_webhooks._get_redis")
    @patch("src.api.routes.email_webhooks.queue_source_event", return_value="task-new")
    def test_new_message_id_processed(
        self,
        mock_queue: MagicMock,
        mock_redis: MagicMock,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
        email_source: FeedbackSource,
    ):
        """Should process email with a never-seen Message-ID."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.get.return_value = None  # not seen
        mock_redis_instance.incr.return_value = 1
        mock_redis.return_value = mock_redis_instance

        payload = _make_inbound_payload(message_id="<brand-new@mail.com>")
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"

        # Verify dedup key was set in Redis
        mock_redis_instance.setex.assert_called()


# ============================================================================
# Webhook Signature Verification Tests
# ============================================================================

class TestWebhookSignatureVerification:
    """Tests for svix webhook signature verification."""

    @patch("src.api.routes.email_webhooks._verify_webhook_signature", return_value=False)
    def test_invalid_signature_returns_401(
        self,
        mock_verify: MagicMock,
        client: TestClient,
        db: Session,
        email_source: FeedbackSource,
    ):
        """Should return 401 when webhook signature verification fails."""
        payload = _make_inbound_payload()
        response = client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload,
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid webhook signature"

    @patch("src.api.routes.email_webhooks.RESEND_INBOUND_WEBHOOK_SECRET", None)
    def test_missing_secret_skips_verification(
        self,
        client: TestClient,
        db: Session,
        email_source: FeedbackSource,
    ):
        """Should skip verification and continue when webhook secret is not configured."""
        from src.api.routes.email_webhooks import _verify_webhook_signature

        result = _verify_webhook_signature(b'{"test": true}', {})
        assert result is True
