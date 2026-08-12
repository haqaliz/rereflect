"""
Tests for worker outreach_sender — opt-out, cooldown, List-Unsubscribe,
token composition (outreach-core aspect).

Strict TDD: written FIRST (RED) before the implementation.
Redis cooldown is exercised via `_get_redis` patching (no live Redis needed,
mirroring test_automation_churn_trigger.py). Sends go through the worker's
`src.email._send_email`, patched here — no live Resend calls.
"""

import ast
import hashlib
import hmac
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import CustomerHealth

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_health(db, org_id, email, *, opted_out=False, **kwargs):
    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        outreach_opt_out=opted_out,
        **kwargs,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _no_cooldown_redis():
    """A fake Redis client that always reports 'not in cooldown'."""
    m = MagicMock()
    m.exists.return_value = False
    return m


# ---------------------------------------------------------------------------
# Token composition (worker mirror — must stay byte-compatible with the
# backend's canonical outreach_tokens.py so the endpoint can verify it)
# ---------------------------------------------------------------------------


class TestMakeUnsubscribeToken:
    def test_token_embeds_normalized_org_email_and_hmac_digest(self):
        from src.services.outreach_sender import make_unsubscribe_token

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": "test-secret"}):
            token = make_unsubscribe_token(7, " Alice@Example.COM ")

        prefix, sep, digest = token.rpartition(":")
        assert sep == ":"
        assert prefix == "7:alice@example.com", (
            "token prefix must be '<org_id>:<normalized email>' so the endpoint "
            "can recover org+email without extra state"
        )
        expected = hmac.new(
            b"test-secret",
            b"7:alice@example.com",
            hashlib.sha256,
        ).hexdigest()
        assert digest == expected

    def test_raises_valueerror_without_encryption_key(self):
        from src.services.outreach_sender import make_unsubscribe_token

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError):
                make_unsubscribe_token(1, "alice@example.com")


# ---------------------------------------------------------------------------
# send_outreach_email contract (AC3-AC6)
# ---------------------------------------------------------------------------


class TestSendOutreachEmail:
    @patch("src.email.RESEND_API_KEY", "re_test_key")
    @patch("src.email._send_email")
    @patch("src.services.outreach_sender._get_redis", return_value=None)
    def test_opted_out_customer_skipped_without_api_call(
        self, mock_redis, mock_send, db
    ):
        """AC3 — opted-out customer -> skipped: opted out, no API call made."""
        from src.services.outreach_sender import send_outreach_email

        _make_health(db, 1, "alice@example.com", opted_out=True)

        result = send_outreach_email(
            db, 1, " ALICE@Example.COM ", "Subj", "Body", product_name="Acme"
        )

        assert result == {"ok": False, "status": "skipped", "reason": "opted out"}
        mock_send.assert_not_called()

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    @patch("src.email._send_email")
    def test_in_cooldown_skipped(self, mock_send, db):
        """AC4 — Redis key present -> skipped: in cooldown."""
        from src.services.outreach_sender import send_outreach_email

        fake = _no_cooldown_redis()
        fake.exists.return_value = True
        with patch("src.services.outreach_sender._get_redis", return_value=fake):
            result = send_outreach_email(
                db, 1, "alice@example.com", "Subj", "Body", product_name="Acme"
            )

        assert result == {"ok": False, "status": "skipped", "reason": "in cooldown"}
        fake.exists.assert_called_once_with("outreach_cooldown:1:alice@example.com")
        mock_send.assert_not_called()

    @patch("src.email.RESEND_API_KEY", None)
    @patch("src.email._send_email")
    def test_no_key_failed_email_not_configured(self, mock_send, db):
        """AC5 — RESEND_API_KEY unset -> failed: email not configured, no exception."""
        from src.services.outreach_sender import send_outreach_email

        result = send_outreach_email(
            db, 1, "alice@example.com", "Subj", "Body", product_name="Acme"
        )

        assert result == {
            "ok": False,
            "status": "failed",
            "reason": "email not configured",
        }
        mock_send.assert_not_called()

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    def test_success_sets_cooldown_and_sends_with_list_unsubscribe(self, db):
        """AC6 — successful send sets the cooldown key (DB 1, TTL
        OUTREACH_COOLDOWN_HOURS) and the payload carries List-Unsubscribe."""
        import re

        from src.services.outreach_sender import send_outreach_email

        fake = _no_cooldown_redis()
        with patch(
            "src.services.outreach_sender._get_redis", return_value=fake
        ), patch("src.email._send_email", return_value=True) as mock_send, patch(
            "src.email.APP_URL", "https://app.example.com"
        ), patch.dict(
            os.environ,
            {"LLM_ENCRYPTION_KEY": "test-secret", "OUTREACH_COOLDOWN_HOURS": "24"},
        ):
            result = send_outreach_email(
                db, 1, "alice@example.com", "Subj", "Body", product_name="Acme"
            )

        assert result == {"ok": True, "status": "sent", "reason": ""}
        fake.setex.assert_called_once_with(
            "outreach_cooldown:1:alice@example.com", 24 * 3600, "1"
        )
        call = mock_send.call_args
        assert call.kwargs["to"] == "alice@example.com"
        headers = call.kwargs["extra_headers"]
        header_url = headers["List-Unsubscribe"]
        assert re.fullmatch(
            r"<https://app\.example\.com/outreach/unsubscribe"
            r"\?token=1:alice@example\.com:[0-9a-f]{64}>",
            header_url,
        ), f"unexpected List-Unsubscribe header: {header_url!r}"
        assert call.kwargs["text"] == "Body"

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    def test_cooldown_ttl_honors_env_override(self, db):
        from src.services.outreach_sender import send_outreach_email

        fake = _no_cooldown_redis()
        with patch(
            "src.services.outreach_sender._get_redis", return_value=fake
        ), patch("src.email._send_email", return_value=True), patch(
            "src.email.APP_URL", "https://app.example.com"
        ), patch.dict(
            os.environ,
            {"LLM_ENCRYPTION_KEY": "test-secret", "OUTREACH_COOLDOWN_HOURS": "6"},
        ):
            send_outreach_email(db, 1, "alice@example.com", "S", "B", product_name="Acme")

        fake.setex.assert_called_once_with(
            "outreach_cooldown:1:alice@example.com", 6 * 3600, "1"
        )

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    def test_unparseable_cooldown_hours_falls_back_to_24(self, db):
        from src.services.outreach_sender import send_outreach_email

        fake = _no_cooldown_redis()
        with patch(
            "src.services.outreach_sender._get_redis", return_value=fake
        ), patch("src.email._send_email", return_value=True), patch(
            "src.email.APP_URL", "https://app.example.com"
        ), patch.dict(
            os.environ,
            {"LLM_ENCRYPTION_KEY": "test-secret", "OUTREACH_COOLDOWN_HOURS": "nope"},
        ):
            send_outreach_email(db, 1, "alice@example.com", "S", "B", product_name="Acme")

        fake.setex.assert_called_once_with(
            "outreach_cooldown:1:alice@example.com", 24 * 3600, "1"
        )

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    def test_send_failure_returns_failed_and_does_not_set_cooldown(self, db):
        from src.services.outreach_sender import send_outreach_email

        fake = _no_cooldown_redis()
        with patch(
            "src.services.outreach_sender._get_redis", return_value=fake
        ), patch("src.email._send_email", return_value=False), patch(
            "src.email.APP_URL", "https://app.example.com"
        ), patch.dict(
            os.environ,
            {"LLM_ENCRYPTION_KEY": "test-secret", "OUTREACH_COOLDOWN_HOURS": "24"},
        ):
            result = send_outreach_email(
                db, 1, "alice@example.com", "Subj", "Body", product_name="Acme"
            )

        assert result == {
            "ok": False,
            "status": "failed",
            "reason": "resend send failed",
        }
        fake.setex.assert_not_called()

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    def test_redis_unavailable_still_sends(self, db):
        """_get_redis() -> None degrades cooldowns to 'always send', never raises."""
        from src.services.outreach_sender import send_outreach_email

        with patch("src.services.outreach_sender._get_redis", return_value=None), patch(
            "src.email._send_email", return_value=True
        ), patch("src.email.APP_URL", "https://app.example.com"), patch.dict(
            os.environ,
            {"LLM_ENCRYPTION_KEY": "test-secret", "OUTREACH_COOLDOWN_HOURS": "24"},
        ):
            result = send_outreach_email(
                db, 1, "alice@example.com", "Subj", "Body", product_name="Acme"
            )

        assert result == {"ok": True, "status": "sent", "reason": ""}


# ---------------------------------------------------------------------------
# Worker _send_email additive params (Phase 3) — byte-compatible default
# ---------------------------------------------------------------------------


class TestWorkerSendEmailExtraParams:
    @patch("src.email.RESEND_API_KEY", "re_test_key")
    @patch("src.email.requests.post")
    def test_forwards_extra_headers_and_text(self, mock_post):
        from src.email import _send_email

        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {"id": "em_1"}

        ok = _send_email(
            "a@b.c",
            "Subject",
            "<p>hi</p>",
            extra_headers={"List-Unsubscribe": "<https://app.example.com/u>"},
            text="hi plain",
        )
        assert ok is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["headers"] == {"List-Unsubscribe": "<https://app.example.com/u>"}
        assert payload["text"] == "hi plain"
        assert payload["html"] == "<p>hi</p>"

    @patch("src.email.RESEND_API_KEY", "re_test_key")
    @patch("src.email.requests.post")
    def test_default_payload_unchanged(self, mock_post):
        from src.email import _send_email

        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {"id": "em_1"}

        _send_email("a@b.c", "Subject", "<p>hi</p>")
        payload = mock_post.call_args.kwargs["json"]
        assert "headers" not in payload
        assert "text" not in payload


# ---------------------------------------------------------------------------
# Cooldown-key agreement pin (Phase 3 step 6) — the worker mirror's prefix
# must stay identical to backend's outreach_sender_contract constant.
# Both suites pin the literal "outreach_cooldown:{org_id}:{customer_email}"
# scheme independently; if one side drifts, its own suite fails.
# ---------------------------------------------------------------------------


class TestCooldownKeySchemePin:
    def test_prefix_literal_and_key_scheme(self):
        from src.services.outreach_sender import OUTREACH_COOLDOWN_PREFIX

        assert OUTREACH_COOLDOWN_PREFIX == "outreach_cooldown"
        assert (
            f"{OUTREACH_COOLDOWN_PREFIX}:7:alice@example.com"
            == "outreach_cooldown:7:alice@example.com"
        )


# ---------------------------------------------------------------------------
# Import sweep (Phase 3 step 5) — outreach modules must import only
# worker-local code (mirrors test_worker_import_sweep.py for this aspect).
# ---------------------------------------------------------------------------


class TestOutreachModulesImportSweep:
    BANNED = [
        "src.api",
        "src.utils",
        "src.services.automation_engine",
        "src.services.health_score_service",
        "src.models.feedback_workflow_event",
    ]

    def test_outreach_modules_exist_and_import_nothing_banned(self):
        src_services = Path(__file__).resolve().parents[1] / "src" / "services"
        for name in ("outreach_sender.py", "outreach_templates_mirror.py"):
            path = src_services / name
            assert path.exists(), f"{name} is missing — the sweep must cover it"
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, ast.Import):
                    targets = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    targets = [node.module] if node.module else []
                for target in targets:
                    for banned in self.BANNED:
                        assert not (
                            target == banned or target.startswith(banned + ".")
                        ), f"{name} imports banned backend path {banned!r}"
