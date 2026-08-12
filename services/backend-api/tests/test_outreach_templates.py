"""
Tests for the outreach template registry + GET /api/v1/outreach/templates.

Strict TDD: written FIRST (RED) before the registry/endpoint implementation.
Also pins the additive `extra_headers`/`text` params on the backend
`_send_email` copies (Phase 3, outreach-core) and the backend's cooldown
prefix contract constant.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.playbook_seeder import SEED_TEMPLATES


# ---------------------------------------------------------------------------
# Registry unit tests
# ---------------------------------------------------------------------------


class TestOutreachRegistry:
    def test_has_both_required_keys(self):
        from src.services.outreach_templates import OUTREACH_TEMPLATES

        assert "re_engagement" in OUTREACH_TEMPLATES
        assert "weekly_digest_entry" in OUTREACH_TEMPLATES

    def test_each_template_has_non_empty_fields(self):
        from src.services.outreach_templates import OUTREACH_TEMPLATES

        for key in ("re_engagement", "weekly_digest_entry"):
            tpl = OUTREACH_TEMPLATES[key]
            assert tpl.key == key
            assert tpl.label.strip()
            assert tpl.description.strip()
            assert tpl.subject.strip()
            assert tpl.body.strip()

    def test_seeded_send_email_template_keys_are_registered(self):
        """The playbook seeder ships send_email steps whose template config must
        resolve in the registry — the At-Risk Outreach + Silent-Churn Watch
        seeds (playbook_seeder.py:111,215) must not reference unknown keys."""
        from src.services.outreach_templates import OUTREACH_TEMPLATES

        seeded_keys = {
            action["config"]["template"]
            for tpl in SEED_TEMPLATES
            for action in tpl["action_sequence"]
            if action["type"] == "send_email"
        }
        assert seeded_keys == {"re_engagement", "weekly_digest_entry"}
        assert seeded_keys <= set(OUTREACH_TEMPLATES.keys())


class TestRenderOutreachTemplate:
    def test_substitutes_customer_and_product_names(self):
        from src.services.outreach_templates import render_outreach_template

        body = render_outreach_template(
            "re_engagement", "Alice", "Acme Analytics"
        )
        assert "Alice" in body
        assert "Acme Analytics" in body
        assert "{{CUSTOMER_NAME}}" not in body
        assert "{{PRODUCT_NAME}}" not in body

    def test_leaves_unknown_placeholders_untouched(self, monkeypatch):
        from src.services import outreach_templates as mod
        from src.services.outreach_templates import OutreachTemplate

        synthetic = OutreachTemplate(
            key="synthetic",
            label="x",
            description="x",
            subject="x",
            body="Hi {{CUSTOMER_NAME}}, welcome to {{PRODUCT_NAME}} — see {{MYSTERY_VAR}} now",
        )
        monkeypatch.setitem(mod.OUTREACH_TEMPLATES, "synthetic", synthetic)
        rendered = mod.render_outreach_template("synthetic", "Bob", "Acme")
        assert "Bob" in rendered
        assert "Acme" in rendered
        assert "{{MYSTERY_VAR}}" in rendered
        assert "{{CUSTOMER_NAME}}" not in rendered
        assert "{{PRODUCT_NAME}}" not in rendered

    def test_unknown_key_raises_keyerror(self):
        from src.services.outreach_templates import render_outreach_template

        try:
            render_outreach_template("no_such_template", "A", "B")
        except KeyError:
            pass
        else:
            raise AssertionError(
                "render_outreach_template must raise KeyError for an unknown key"
            )


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestTemplatesEndpoint:
    def test_authed_returns_both_keys_with_label_description(
        self, client, test_user, auth_headers
    ):
        response = client.get("/api/v1/outreach/templates", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        keys = {item["key"] for item in data}
        assert keys == {"re_engagement", "weekly_digest_entry"}
        for item in data:
            assert item["label"]
            assert item["description"]

    def test_member_role_can_read(self, client, db, test_organization, test_user):
        from src.models.user import User
        from src.api.auth import create_access_token

        member = User(
            email="member@example.com",
            password_hash="x",
            organization_id=test_organization.id,
            role="member",
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        token = create_access_token({
            "user_id": member.id,
            "organization_id": member.organization_id,
            "role": member.role,
        })
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/v1/outreach/templates", headers=headers)
        assert response.status_code == 200
        keys = {item["key"] for item in response.json()}
        assert keys == {"re_engagement", "weekly_digest_entry"}

    def test_unauthed_returns_401(self, client):
        response = client.get("/api/v1/outreach/templates")
        # HTTPBearer returns 403 when no token is sent (repo convention,
        # documented in test_customers.py:137).
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Backend _send_email additive params (outreach-core Phase 3)
# extra_headers/text must land in the Resend payload and default callers must
# stay byte-compatible (no headers/text keys when not passed).
# ---------------------------------------------------------------------------


class TestBackendSendEmailPayloadParams:
    @pytest.fixture(autouse=True)
    def _restore_real_send_email(self):
        """conftest's autouse `_disable_emails` fixture swaps `_send_email` for a
        True-returning mock. These tests pin the Resend payload shape, so restore
        the real implementation and mock the transport (`requests.post`) instead —
        no real email can leave the process."""
        import importlib

        from src.services import email_service as es_mod

        importlib.reload(es_mod)
        yield

    @patch("src.services.email_service.RESEND_API_KEY", "re_test_key")
    @patch("src.services.email_service.requests.post")
    def test_send_email_forwards_extra_headers_and_text(self, mock_post):
        from src.services import email_service

        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {"id": "em_1"}

        ok = email_service._send_email(
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

    @patch("src.services.email_service.RESEND_API_KEY", "re_test_key")
    @patch("src.services.email_service.requests.post")
    def test_send_email_default_payload_unchanged(self, mock_post):
        from src.services import email_service

        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {"id": "em_1"}

        email_service._send_email("a@b.c", "Subject", "<p>hi</p>")
        payload = mock_post.call_args.kwargs["json"]
        assert "headers" not in payload
        assert "text" not in payload

    @patch("src.services.email_service.RESEND_API_KEY", "re_test_key")
    @patch("src.services.email_service.requests.post")
    def test_send_email_with_from_forwards_extra_headers_and_text(self, mock_post):
        from src.services import email_service

        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {"id": "em_1"}

        ok = email_service._send_email_with_from(
            "a@b.c",
            "Subject",
            "<p>hi</p>",
            "alerts@example.com",
            extra_headers={"List-Unsubscribe": "<https://app.example.com/u>"},
            text="hi plain",
        )
        assert ok is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["from"] == "alerts@example.com"
        assert payload["headers"] == {"List-Unsubscribe": "<https://app.example.com/u>"}
        assert payload["text"] == "hi plain"


# ---------------------------------------------------------------------------
# Cooldown-prefix agreement pin (outreach-core Phase 3 step 6)
# The backend contract constant must agree with the worker's
# OUTREACH_COOLDOWN_PREFIX so both send paths write the same Redis key.
# ---------------------------------------------------------------------------


class TestBackendCooldownPrefixPin:
    def test_outreach_cooldown_prefix_contract(self):
        from src.services.outreach_sender_contract import OUTREACH_COOLDOWN_PREFIX

        assert OUTREACH_COOLDOWN_PREFIX == "outreach_cooldown"
        assert (
            f"{OUTREACH_COOLDOWN_PREFIX}:7:alice@example.com"
            == "outreach_cooldown:7:alice@example.com"
        )
