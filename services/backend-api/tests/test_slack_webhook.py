"""Tests for the Slack Events API webhook signature verification.

Slack ingestion has live production traffic (unlike Intercom, whose ingestion
never worked because of a separate envelope-shape bug — see test_intercom.py's
TestVerifyIntercomSignatureFailsClosed for the fail-closed treatment there).
It shipped in shadow mode for a grace period (keep accepting, but log
loudly) so operators could set SLACK_SIGNING_SECRET before enforcement. That
grace period ended 2026-08-17: the verifier now fails closed like the other
five — an unset secret rejects the delivery with 401.
"""
import hashlib
import hmac
import json
import time

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _make_slack_signature(body: str, timestamp: str, secret: str) -> str:
    sig_basestring = f"v0:{timestamp}:{body}"
    return "v0=" + hmac.new(
        secret.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()


class TestVerifySlackSignatureFailClosed:
    """Unit-level coverage of verify_slack_signature's unset-secret path."""

    def test_missing_secret_rejects(self, caplog: pytest.LogCaptureFixture):
        """Fail closed: an unset secret must return False (reject), logging
        the non-shadow warning that names the missing variable."""
        from src.api.routes.source_webhooks import verify_slack_signature

        with caplog.at_level("WARNING"):
            result = verify_slack_signature(
                body="{}", timestamp=str(int(time.time())), signature="v0=whatever", secret=""
            )

        assert result is False
        assert any(
            "SLACK_SIGNING_SECRET not configured, rejecting webhook (fails closed)"
            in record.message
            for record in caplog.records
        )


class TestSlackWebhookFailClosed:
    """Tests for POST /api/v1/webhooks/slack/events signature handling."""

    @patch("src.api.routes.source_webhooks.SLACK_SIGNING_SECRET", "")
    def test_unset_secret_rejects_request(self, client: TestClient):
        """With SLACK_SIGNING_SECRET unset, an unsigned request is rejected
        with 401 — fail closed, matching the other webhook verifiers."""
        payload = {"type": "url_verification", "challenge": "abc123"}
        body = json.dumps(payload)

        response = client.post(
            "/api/v1/webhooks/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=whatever",
            },
        )

        assert response.status_code == 401

    @patch("src.api.routes.source_webhooks.SLACK_SIGNING_SECRET", "real-secret")
    def test_configured_secret_rejects_bad_signature(self, client: TestClient):
        """Once SLACK_SIGNING_SECRET is configured, a bad signature is
        rejected — shadow mode only relaxes the unconfigured case."""
        payload = {"type": "url_verification", "challenge": "abc123"}
        body = json.dumps(payload)

        response = client.post(
            "/api/v1/webhooks/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=wrong-signature",
            },
        )

        assert response.status_code == 401

    @patch("src.api.routes.source_webhooks.SLACK_SIGNING_SECRET", "real-secret")
    def test_configured_secret_accepts_valid_signature(self, client: TestClient):
        """A correctly signed request with the secret configured is accepted,
        proving the shadow-mode logging change didn't disturb the real
        verification path."""
        payload = {"type": "url_verification", "challenge": "abc123"}
        body = json.dumps(payload)
        timestamp = str(int(time.time()))
        signature = _make_slack_signature(body, timestamp, "real-secret")

        response = client.post(
            "/api/v1/webhooks/slack/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )

        assert response.status_code == 200
        assert response.json()["challenge"] == "abc123"
