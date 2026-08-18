"""
Tests for the stateless OAuth `state` signing helpers (src/services/oauth_state.py).

Shared by the Slack, Intercom and Linear OAuth flows. Fail-closed contract:
any invalid/forged/expired state verifies to None, never to a payload.
"""

import base64
import json
import time

import pytest
from unittest.mock import patch

from src.services.oauth_state import STATE_TTL_SECONDS, sign_oauth_state, verify_oauth_state


class TestSignVerifyRoundTrip:
    def test_sign_and_verify_round_trip(self):
        """A signed state verifies back to the exact payload (org + name + exp)."""
        state = sign_oauth_state(organization_id=42, name="My Slack")
        payload = verify_oauth_state(state)
        assert payload is not None
        assert payload["organization_id"] == 42
        assert payload["name"] == "My Slack"
        assert "nonce" in payload
        assert abs(payload["exp"] - (time.time() + STATE_TTL_SECONDS)) < 5

    def test_sign_round_trip_keeps_optional_user_id(self):
        """Linear carries user_id in the signed blob; the others omit it."""
        state = sign_oauth_state(organization_id=42, name="Linear", user_id=7)
        payload = verify_oauth_state(state)
        assert payload["user_id"] == 7

        state = sign_oauth_state(organization_id=42, name="Intercom")
        payload = verify_oauth_state(state)
        assert "user_id" not in payload

    def test_signature_is_stateless_and_deterministic_in_shape(self):
        """Every state carries an HMAC signature after a '.' separator."""
        state = sign_oauth_state(organization_id=1, name="x")
        payload_b64, _, sig = state.rpartition(".")
        assert payload_b64 and sig
        assert len(sig) == 64  # sha256 hexdigest


class TestVerifyFailClosed:
    def test_verify_tampered_payload_returns_none(self):
        """A payload byte changed after signing (sig not re-computed) → None."""
        state = sign_oauth_state(organization_id=42, name="My Slack")
        payload_b64, _, sig = state.rpartition(".")
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        payload["organization_id"] = 43
        forged_b64 = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        forged = f"{forged_b64}.{sig}"
        assert forged != state
        assert verify_oauth_state(forged) is None

    def test_verify_tampered_signature_returns_none(self):
        """A signature byte changed → None."""
        state = sign_oauth_state(organization_id=42, name="My Slack")
        payload_b64, _, sig = state.rpartition(".")
        flipped = ("0" if sig[0] != "0" else "1") + sig[1:]
        assert verify_oauth_state(f"{payload_b64}.{flipped}") is None

    def test_verify_signed_under_wrong_secret_returns_none(self):
        """A state minted with a different app secret must not verify."""
        state = sign_oauth_state(organization_id=42, name="My Slack")
        with patch("src.api.auth.JWT_SECRET", "another-secret"):
            assert verify_oauth_state(state) is None

    def test_verify_expired_returns_none(self):
        """A state signed 10 minutes ago (TTL elapsed) → None."""
        with patch("src.services.oauth_state.time.time", return_value=1_000_000_000):
            state = sign_oauth_state(organization_id=42, name="My Slack")
        # exp = 1_000_000_000 + 600, long past by now
        assert verify_oauth_state(state) is None

    def test_verify_within_ttl_succeeds(self):
        """A state signed 9 minutes ago still verifies (boundary inside the TTL)."""
        with patch("src.services.oauth_state.time.time", return_value=1_000_000_000):
            state = sign_oauth_state(organization_id=42, name="My Slack")
        with patch("src.services.oauth_state.time.time", return_value=1_000_000_000 + 540):
            payload = verify_oauth_state(state)
        assert payload is not None
        assert payload["organization_id"] == 42

    @pytest.mark.parametrize("garbage", ["", "bad-state", "a.b.c.d", "no dot here"])
    def test_verify_garbage_returns_none(self, garbage):
        """Malformed states — missing, dotless, or over-split — → None."""
        assert verify_oauth_state(garbage) is None

    def test_verify_non_json_payload_returns_none(self):
        """A validly-signed payload that is not JSON → None (no 500)."""
        payload_b64 = base64.urlsafe_b64encode(b"not-json").decode().rstrip("=")
        import hashlib
        import hmac
        from src.api.auth import JWT_SECRET
        sig = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        assert verify_oauth_state(f"{payload_b64}.{sig}") is None
