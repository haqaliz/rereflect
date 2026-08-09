"""TDD tests for send_slack_alert() OAuth token decryption (worker decrypt mirrors).

The backend encrypts Slack OAuth tokens at rest in `integrations.oauth_access_token`
(oauth-tokens-encryption-at-rest). The worker image cannot import backend-api
(`src.utils.encryption` does not exist there), so every read site must decrypt with
its own module-local Fernet helper.

These tests pin the alert send path:
  * the PLAINTEXT token must reach send_slack_message_oauth (never the ciphertext);
  * a missing LLM_ENCRYPTION_KEY or corrupt ciphertext must return the error dict
    contract WITHOUT retrying (config error, not transient) and WITHOUT raising
    out of the task.

See docs/planning/oauth-tokens-encryption-at-rest/worker-decrypt-mirrors/.
"""
import os
from unittest.mock import patch, MagicMock

from src.models import Organization, Integration, FeedbackItem

ENCRYPTION_KEY = "F5XVApZxzOVKc2xrZlnI6ouXipDzsxflzFn2Ki_5_yk="


def _encrypt(secret: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(ENCRYPTION_KEY.encode()).encrypt(secret.encode()).decode()


def _make_org(db) -> Organization:
    org = Organization(name="Alert Co", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_oauth_integration(db, org_id: int, token: str) -> Integration:
    integ = Integration(
        organization_id=org_id,
        type="slack",
        config={"integration_type": "oauth", "channel_id": "C123"},
        oauth_access_token=token,
        is_active=True,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _make_feedback(db, org_id: int) -> FeedbackItem:
    item = FeedbackItem(
        organization_id=org_id,
        text="Billing is broken",
        source="email",
        sentiment_label="negative",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _call_send_slack_alert(db, integration_id, feedback_ids, org_id):
    from src.tasks.alerts import send_slack_alert

    with patch("src.tasks.alerts.get_db_session") as mock_ctx:
        mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        with patch("src.tasks.alerts.log_alert"):
            return send_slack_alert(
                integration_id=integration_id,
                feedback_ids=feedback_ids,
                org_id=org_id,
            )


class TestSendSlackAlertOAuthDecrypt:
    """send_slack_alert must decrypt the stored token exactly once, at send time."""

    def test_plaintext_token_reaches_send_slack_message_oauth(self, db):
        from src.tasks.alerts import send_slack_alert

        org = _make_org(db)
        item = _make_feedback(db, org.id)
        integ = _make_oauth_integration(db, org.id, _encrypt("xoxb-plain-secret"))
        # Truthiness-trap guard: the stored value really is ciphertext, and the
        # truthiness checks must keep working on it.
        assert "xoxb-plain-secret" not in integ.oauth_access_token
        assert integ.oauth_access_token  # truthy ciphertext

        with patch("src.tasks.alerts.get_db_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=db)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            with patch("src.tasks.alerts.log_alert"):
                with patch(
                    "src.tasks.alerts.send_slack_message_oauth",
                    return_value={"success": True},
                ) as mock_send:
                    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ENCRYPTION_KEY}):
                        result = send_slack_alert(
                            integration_id=integ.id,
                            feedback_ids=[item.id],
                            org_id=org.id,
                        )

        assert result["status"] == "sent"
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["access_token"] == "xoxb-plain-secret"
        assert mock_send.call_args.kwargs["channel_id"] == "C123"

    def test_missing_key_returns_error_dict_without_sending(self, db):
        org = _make_org(db)
        item = _make_feedback(db, org.id)
        integ = _make_oauth_integration(db, org.id, _encrypt("xoxb-plain-secret"))

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ""}):
            with patch("src.tasks.alerts.send_slack_message_oauth") as mock_send:
                result = _call_send_slack_alert(db, integ.id, [item.id], org.id)

        assert result == {"status": "error", "reason": "token_decrypt_failed"}
        mock_send.assert_not_called()

    def test_corrupt_ciphertext_returns_error_dict_without_sending(self, db):
        org = _make_org(db)
        item = _make_feedback(db, org.id)
        integ = _make_oauth_integration(db, org.id, "garbage-not-fernet")

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ENCRYPTION_KEY}):
            with patch("src.tasks.alerts.send_slack_message_oauth") as mock_send:
                result = _call_send_slack_alert(db, integ.id, [item.id], org.id)

        assert result == {"status": "error", "reason": "token_decrypt_failed"}
        mock_send.assert_not_called()
