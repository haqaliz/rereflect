"""
TDD tests for the deliver_webhook Celery task (M3.1 Phase 2).

Tests are written first; the implementation at
src/tasks/webhook_delivery.py must make them pass.
"""

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock sentry_sdk and src.celery_app before importing any task module.
# Follows the same pattern as conftest.py (which already mocks src.config
# and src.database).
# ---------------------------------------------------------------------------
_mock_sentry = MagicMock()
sys.modules.setdefault("sentry_sdk", _mock_sentry)
sys.modules.setdefault("sentry_sdk.integrations", _mock_sentry)
sys.modules.setdefault("sentry_sdk.integrations.celery", _mock_sentry)

_mock_celery_app = MagicMock()
_mock_celery_module = MagicMock()
_mock_celery_module.celery_app = _mock_celery_app
sys.modules.setdefault("src.celery_app", _mock_celery_module)

# ---------------------------------------------------------------------------
# Ensure encryption key env var is set before any src import
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "LLM_ENCRYPTION_KEY",
    "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY=",
)

# ---------------------------------------------------------------------------
# Provide a minimal Fernet-compatible encrypt/decrypt for this test module
# without depending on the backend-api src tree.
# The worker duplicates its own encryption helper OR we can provide it here.
# ---------------------------------------------------------------------------
from cryptography.fernet import Fernet as _Fernet


def _fernet_encrypt(plain: str) -> str:
    key = os.environ["LLM_ENCRYPTION_KEY"]
    return _Fernet(key.encode()).encrypt(plain.encode()).decode()


def _fernet_decrypt(token: str) -> str:
    key = os.environ["LLM_ENCRYPTION_KEY"]
    return _Fernet(key.encode()).decrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def raw_secret() -> str:
    return "supersecret_hmac_key_abc123"


@pytest.fixture
def sample_payload() -> dict:
    return {
        "event": "feedback.created",
        "timestamp": "2026-03-15T14:30:00Z",
        "webhook_id": 42,
        "organization_id": 1,
        "data": {
            "feedback": {
                "id": 2207,
                "text": "The login page is broken",
                "sentiment_label": "negative",
                "sentiment_score": -0.85,
                "tags": ["authentication", "bug"],
                "is_urgent": False,
                "churn_risk_score": 45,
                "pain_point_category": "authentication",
                "feature_request_category": None,
                "workflow_status": "new",
                "assigned_to": None,
                "customer_email": "user@example.com",
                "source": "slack",
                "created_at": "2026-03-15T14:29:55Z",
            }
        },
    }


@pytest.fixture
def webhook_row(db, raw_secret):
    """Create a WebhookEndpoint-like model row in the test DB."""
    # We need to add webhook models to worker's models.py, but for now we
    # import them from the worker's local models after adding them.
    # (The models are added as part of this PR.)
    from src.models import WebhookEndpoint, WebhookDelivery  # noqa — added by this task

    wh = WebhookEndpoint(
        organization_id=1,
        name="Test Hook",
        url="https://example.com/receiver",
        signing_secret=_fernet_encrypt(raw_secret),
        events=["feedback.created"],
        category_filters=[],
        retry_mode="fire_and_forget",
        is_active=True,
        consecutive_failures=0,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


@pytest.fixture
def webhook_row_backoff(db, raw_secret):
    """WebhookEndpoint with exponential_backoff retry mode."""
    from src.models import WebhookEndpoint

    wh = WebhookEndpoint(
        organization_id=1,
        name="Backoff Hook",
        url="https://example.com/receiver-backoff",
        signing_secret=_fernet_encrypt(raw_secret),
        events=["feedback.created"],
        category_filters=[],
        retry_mode="exponential_backoff",
        is_active=True,
        consecutive_failures=0,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


@pytest.fixture
def webhook_row_near_failure(db, raw_secret):
    """WebhookEndpoint at 9 consecutive failures (one away from auto-disable)."""
    from src.models import WebhookEndpoint

    wh = WebhookEndpoint(
        organization_id=1,
        name="Near Failure Hook",
        url="https://example.com/receiver-fail",
        signing_secret=_fernet_encrypt(raw_secret),
        events=["feedback.created"],
        category_filters=[],
        retry_mode="fire_and_forget",
        is_active=True,
        consecutive_failures=9,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


@pytest.fixture
def webhook_row_with_custom_headers(db, raw_secret):
    """WebhookEndpoint with custom headers."""
    from src.models import WebhookEndpoint

    headers = {"Authorization": "Bearer token123", "X-API-Key": "apikey456"}
    wh = WebhookEndpoint(
        organization_id=1,
        name="Custom Headers Hook",
        url="https://example.com/receiver-headers",
        signing_secret=_fernet_encrypt(raw_secret),
        events=["feedback.created"],
        category_filters=[],
        custom_headers=_fernet_encrypt(json.dumps(headers)),
        retry_mode="fire_and_forget",
        is_active=True,
        consecutive_failures=0,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeliverWebhookSuccess:
    """_run_delivery logs a 'sent' delivery on HTTP 200."""

    def test_deliver_webhook_success(self, db, webhook_row, sample_payload):
        """
        When the target URL returns 200, a WebhookDelivery with status='sent'
        is created and consecutive_failures is reset to 0.
        """
        from src.tasks.webhook_delivery import _run_delivery
        from src.models import WebhookDelivery

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = "OK"

        with patch("src.tasks.webhook_delivery.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            _run_delivery(webhook_row.id, sample_payload, 1, db)

        delivery = db.query(WebhookDelivery).filter(
            WebhookDelivery.webhook_id == webhook_row.id
        ).first()
        assert delivery is not None
        assert delivery.status == "sent"
        assert delivery.response_code == 200
        assert delivery.attempt == 1

        db.refresh(webhook_row)
        assert webhook_row.consecutive_failures == 0


class TestDeliverWebhookFailureFireAndForget:
    """_run_delivery with fire_and_forget logs 'failed' and does not retry."""

    def test_deliver_webhook_failure_fire_and_forget(self, db, webhook_row, sample_payload):
        """
        When the target URL returns 500 and retry_mode is fire_and_forget,
        the delivery is logged as 'failed' with no retry attempt.
        """
        from src.tasks.webhook_delivery import _run_delivery
        from src.models import WebhookDelivery

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False
        mock_response.text = "Internal Server Error"

        with patch("src.tasks.webhook_delivery.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            _run_delivery(webhook_row.id, sample_payload, 1, db)

        delivery = db.query(WebhookDelivery).filter(
            WebhookDelivery.webhook_id == webhook_row.id
        ).first()
        assert delivery is not None
        assert delivery.status == "failed"
        assert delivery.response_code == 500


class TestDeliverWebhookFailureWithRetry:
    """_run_delivery with exponential_backoff logs 'retrying' on non-2xx."""

    def test_deliver_webhook_failure_with_retry(
        self, db, webhook_row_backoff, sample_payload
    ):
        """
        When the target returns 500 and retry_mode is exponential_backoff,
        the delivery is logged as 'retrying' (not 'failed') and consecutive_failures
        is incremented.
        """
        from src.tasks.webhook_delivery import _run_delivery
        from src.models import WebhookDelivery

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False
        mock_response.text = "Server Error"

        with patch("src.tasks.webhook_delivery.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            _run_delivery(webhook_row_backoff.id, sample_payload, 1, db)

        delivery = db.query(WebhookDelivery).filter(
            WebhookDelivery.webhook_id == webhook_row_backoff.id
        ).first()
        assert delivery is not None
        assert delivery.status == "retrying"


class TestDeliverWebhookHmacSignature:
    """X-Rereflect-Signature header is correct HMAC-SHA256 of the JSON body."""

    def test_deliver_webhook_hmac_signature(
        self, db, webhook_row, sample_payload, raw_secret
    ):
        """
        The X-Rereflect-Signature header must equal
        'sha256=' + hmac_sha256(signing_secret, payload_bytes).hexdigest().
        """
        from src.tasks.webhook_delivery import _run_delivery

        captured_headers: dict = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = "OK"

        def fake_post(url, content, headers, timeout):
            captured_headers.update(headers)
            return mock_response

        with patch("src.tasks.webhook_delivery.httpx") as mock_httpx:
            mock_httpx.post.side_effect = fake_post
            _run_delivery(webhook_row.id, sample_payload, 1, db)

        assert "X-Rereflect-Signature" in captured_headers
        sig_header = captured_headers["X-Rereflect-Signature"]
        assert sig_header.startswith("sha256=")

        # Recompute expected signature
        payload_bytes = json.dumps(sample_payload, default=str).encode()
        expected_hex = hmac.new(
            raw_secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()
        assert sig_header == f"sha256={expected_hex}"


class TestDeliverWebhookCustomHeaders:
    """Custom headers defined on the webhook are forwarded to the target."""

    def test_deliver_webhook_custom_headers(
        self, db, webhook_row_with_custom_headers, sample_payload
    ):
        """
        The HTTP POST must include both the standard headers AND the
        Fernet-decrypted custom headers stored on the webhook.
        """
        from src.tasks.webhook_delivery import _run_delivery

        captured_headers: dict = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = "OK"

        def fake_post(url, content, headers, timeout):
            captured_headers.update(headers)
            return mock_response

        with patch("src.tasks.webhook_delivery.httpx") as mock_httpx:
            mock_httpx.post.side_effect = fake_post
            _run_delivery(
                webhook_row_with_custom_headers.id, sample_payload, 1, db
            )

        assert captured_headers.get("Authorization") == "Bearer token123"
        assert captured_headers.get("X-API-Key") == "apikey456"


class TestAutoDisableAfter10Failures:
    """After 10 consecutive failures the webhook is set to is_active=False."""

    def test_auto_disable_after_10_failures(
        self, db, webhook_row_near_failure, sample_payload
    ):
        """
        A webhook with consecutive_failures=9 that fails one more time should:
        - have consecutive_failures set to 10
        - have is_active set to False
        """
        from src.tasks.webhook_delivery import _run_delivery
        from src.models import WebhookDelivery

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.is_success = False
        mock_response.text = "Service Unavailable"

        with patch("src.tasks.webhook_delivery.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            _run_delivery(webhook_row_near_failure.id, sample_payload, 1, db)

        db.refresh(webhook_row_near_failure)
        assert webhook_row_near_failure.consecutive_failures == 10
        assert webhook_row_near_failure.is_active is False

        delivery = db.query(WebhookDelivery).filter(
            WebhookDelivery.webhook_id == webhook_row_near_failure.id
        ).first()
        assert delivery is not None
        assert delivery.status == "failed"


class TestDeliverWebhookNetworkError:
    """Network exceptions (timeout, connection refused) are handled gracefully."""

    def test_deliver_webhook_network_error(self, db, webhook_row, sample_payload):
        """
        When httpx raises an exception (e.g. ConnectError), the delivery
        is logged as 'failed' with the error_message populated.
        """
        from src.tasks.webhook_delivery import _run_delivery
        from src.models import WebhookDelivery

        with patch("src.tasks.webhook_delivery.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("Connection refused")
            _run_delivery(webhook_row.id, sample_payload, 1, db)

        delivery = db.query(WebhookDelivery).filter(
            WebhookDelivery.webhook_id == webhook_row.id
        ).first()
        assert delivery is not None
        assert delivery.status == "failed"
        assert delivery.error_message is not None
        assert "Connection refused" in delivery.error_message
