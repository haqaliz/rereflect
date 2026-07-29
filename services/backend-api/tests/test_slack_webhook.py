"""Tests for the Slack Events API webhook signature verification.

Slack ingestion has live production traffic (unlike Intercom, whose ingestion
never worked because of a separate envelope-shape bug — see test_intercom.py's
TestVerifyIntercomSignatureFailsClosed for the fail-closed treatment there).
Flipping Slack closed immediately would silently stop real feedback flowing
for any operator who never set SLACK_SIGNING_SECRET, so it gets shadow mode
instead: keep accepting, but log loudly via the SECURITY-SHADOW marker so the
gap is visible, with enforcement to follow in a later release.
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


class TestVerifySlackSignatureShadowMode:
    """Unit-level coverage of verify_slack_signature's unset-secret path."""

    def test_missing_secret_accepts_in_shadow_but_warns(
        self, caplog: pytest.LogCaptureFixture
    ):
        """Shadow mode: an unset secret must still return True (Slack keeps
        accepting live traffic), but must log the SECURITY-SHADOW marker so
        an operator can find and close the gap before enforcement lands."""
        from src.api.routes.source_webhooks import verify_slack_signature

        with caplog.at_level("WARNING"):
            result = verify_slack_signature(
                body="{}", timestamp=str(int(time.time())), signature="v0=whatever", secret=""
            )

        assert result is True
        assert any(
            "SECURITY-SHADOW: signature verification unconfigured" in record.message
            for record in caplog.records
        )


class TestSlackWebhookShadowMode:
    """Tests for POST /api/v1/webhooks/slack/events signature handling."""

    @patch("src.api.routes.source_webhooks.SLACK_SIGNING_SECRET", "")
    def test_unset_secret_accepts_request_and_logs_marker(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ):
        """With SLACK_SIGNING_SECRET unset, an unsigned request is still
        accepted (200) — shadow mode, not fail-closed — but the shadow
        marker must be logged."""
        payload = {"type": "url_verification", "challenge": "abc123"}
        body = json.dumps(payload)

        with caplog.at_level("WARNING"):
            response = client.post(
                "/api/v1/webhooks/slack/events",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Slack-Request-Timestamp": str(int(time.time())),
                    "X-Slack-Signature": "v0=whatever",
                },
            )

        assert response.status_code == 200
        assert response.json()["challenge"] == "abc123"
        assert any(
            "SECURITY-SHADOW: signature verification unconfigured" in record.message
            for record in caplog.records
        )

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
