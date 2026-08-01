"""Two webhook hardening fixes carried over from the auth/tenancy sweep.

`zendesk-replay-window` and `generic-webhook-persists-headers`, both filed in
DEV-TRACKING under "Follow-ups opened by that branch".
"""
import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import pytest


def _iso(offset_seconds: int = 0) -> str:
    """Zendesk sends ISO-8601 with a Z suffix, not a Unix epoch."""
    moment = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")



# ─────────────────────── zendesk-replay-window ────────────────────────────────


class TestZendeskTimestampFreshness:
    """Zendesk sends X-Zendesk-Webhook-Signature-Timestamp and it is fed into
    the HMAC, but nothing ever checked that it was recent.

    Signing over the timestamp proves it was not tampered with. It does NOT
    prove the delivery is not a replay -- an attacker who captured one valid
    delivery could resend it verbatim, forever, and every signature check would
    pass. Content dedup does not help here: `_handle_zendesk_status_change` and
    the reconcile paths run BEFORE any dedup, so a captured "ticket closed"
    delivery can undo manual triage repeatedly.

    Slack's verifier already had the 300-second guard; this brings Zendesk to
    the same standard.
    """

    def _sign(self, body: bytes, timestamp: str, secret: str) -> str:
        return base64.b64encode(
            hmac.new(
                secret.encode(), timestamp.encode() + body, hashlib.sha256
            ).digest()
        ).decode()

    def test_fresh_timestamp_verifies(self):
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        ts = _iso()
        assert (
            _verify_zendesk_signature(body, ts, self._sign(body, ts, "sec"), "sec")
            is True
        )

    def test_stale_timestamp_is_rejected(self):
        """A captured delivery replayed an hour later must not verify."""
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        ts = _iso(-3600)
        assert (
            _verify_zendesk_signature(body, ts, self._sign(body, ts, "sec"), "sec")
            is False
        )

    def test_far_future_timestamp_is_rejected(self):
        """Clock skew is bounded in both directions, as Slack's guard is."""
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        ts = _iso(+3600)
        assert (
            _verify_zendesk_signature(body, ts, self._sign(body, ts, "sec"), "sec")
            is False
        )

    def test_unparseable_timestamp_is_rejected(self):
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        body = b'{"ticket": {"id": 1}}'
        assert (
            _verify_zendesk_signature(body, "not-a-timestamp", "sig", "sec") is False
        )

    def test_still_fails_closed_without_a_secret(self):
        """The pre-existing guarantee must survive the new check."""
        from src.api.routes.source_webhooks import _verify_zendesk_signature

        ts = _iso()
        assert _verify_zendesk_signature(b"{}", ts, "sig", "") is False
        assert _verify_zendesk_signature(b"{}", ts, "sig", None) is False


# ──────────────────── generic-webhook-persists-headers ────────────────────────


class TestGenericWebhookDoesNotPersistSecrets:
    """The generic inbound webhook stored dict(request.headers) verbatim into
    FeedbackSourceEvent.event_data -- including the source's own
    X-Webhook-Secret, which is the credential that authenticates the endpoint.

    Anyone with read access to that table could therefore forge deliveries.
    Storing a credential in an event log is the same defect whether or not the
    table is "internal".
    """

    def test_sensitive_headers_are_stripped(self):
        from src.api.routes.source_webhooks import _safe_headers

        cleaned = _safe_headers(
            {
                "content-type": "application/json",
                "x-webhook-secret": "the-actual-secret",
                "user-agent": "curl/8",
            }
        )

        assert "x-webhook-secret" not in cleaned
        assert cleaned["content-type"] == "application/json"
        assert cleaned["user-agent"] == "curl/8"

    def test_stripping_is_case_insensitive(self):
        """HTTP header names are case-insensitive; a redaction that only
        matches lowercase is not a redaction."""
        from src.api.routes.source_webhooks import _safe_headers

        cleaned = _safe_headers({"X-Webhook-Secret": "s", "X-WEBHOOK-SECRET": "s"})
        assert cleaned == {}

    def test_other_credential_headers_are_stripped_too(self):
        from src.api.routes.source_webhooks import _safe_headers

        cleaned = _safe_headers(
            {
                "authorization": "Bearer abc",
                "x-hub-signature": "sha1=x",
                "x-zendesk-webhook-signature": "sig",
                "cookie": "session=1",
                "accept": "application/json",
            }
        )
        assert set(cleaned) == {"accept"}
