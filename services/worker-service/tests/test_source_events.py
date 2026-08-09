"""Tests for the tenancy guards in `_find_matching_sources` (source_events.py).

Four of five branches (slack, intercom, email, webhook) narrow the base
query -- which only filters on `source_type` + `is_active`, with **no**
`organization_id` predicate -- only when a payload-supplied discriminator
(team_id, workspace_id, source_id) is truthy. None of them guarded the
falsy case, so a missing or empty-string discriminator fell through to
`return query.all()` at the end of the function: every org's active
sources of that type, fanned back to whichever org's payload happened to
omit (or blank) the field. Only the zendesk branch already guarded this
(`if not subdomain: return []`); it is included here only as a regression
check that this fix did not touch it.

Each branch gets three tests: missing discriminator, empty-string
discriminator, and a positive case proving the guard didn't also break
legitimate resolution.
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.models import Organization, FeedbackSource, Integration, ZendeskIntegration

ENCRYPTION_KEY = "F5XVApZxzOVKc2xrZlnI6ouXipDzsxflzFn2Ki_5_yk="


def _encrypt(secret: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(ENCRYPTION_KEY.encode()).encrypt(secret.encode()).decode()


# ---------------------------------------------------------------------------
# Fixture helpers -- mirrors tests/test_zendesk_adapter.py's local-helper
# style; the worker suite has no shared org factory.
# ---------------------------------------------------------------------------


def _make_org(db, name="Acme Co") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_slack_integration(db, org_id, team_id="T123", is_active=True) -> Integration:
    integ = Integration(
        organization_id=org_id,
        type="slack",
        config={"team_id": team_id},
        is_active=is_active,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _make_intercom_integration(db, org_id, workspace_id="abc123", is_active=True) -> Integration:
    integ = Integration(
        organization_id=org_id,
        type="intercom",
        config={"workspace_id": workspace_id},
        is_active=is_active,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _make_source(db, org_id, source_type, integration_id=None, is_active=True) -> FeedbackSource:
    source = FeedbackSource(
        organization_id=org_id,
        integration_id=integration_id,
        source_type=source_type,
        is_active=is_active,
        auto_import=True,
        triggers={},
        field_mapping={},
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _make_zendesk_integration(db, org_id, subdomain="acmeco", is_active=True) -> ZendeskIntegration:
    integ = ZendeskIntegration(
        organization_id=org_id,
        subdomain=subdomain,
        email="agent@acmeco.com",
        api_token="enc:blob",
        is_active=is_active,
        connected_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


# ---------------------------------------------------------------------------
# Slack -- discriminator: team_id (via Integration.config)
# ---------------------------------------------------------------------------


class TestSlackTenancyGuard:
    def test_missing_team_id_returns_empty_not_cross_tenant_fanout(self, db):
        """A missing team_id in provider_context must never fall through to
        `return query.all()`, which would fan every org's active slack
        FeedbackSource back to the caller -- a cross-tenant leak."""
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        integ_a = _make_slack_integration(db, org_a.id, team_id="Ta")
        integ_b = _make_slack_integration(db, org_b.id, team_id="Tb")
        _make_source(db, org_a.id, "slack", integration_id=integ_a.id)
        _make_source(db, org_b.id, "slack", integration_id=integ_b.id)

        result = _find_matching_sources(db, "slack", {})

        assert result == []

    def test_empty_string_team_id_returns_empty_not_cross_tenant_fanout(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        integ_a = _make_slack_integration(db, org_a.id, team_id="Ta")
        integ_b = _make_slack_integration(db, org_b.id, team_id="Tb")
        _make_source(db, org_a.id, "slack", integration_id=integ_a.id)
        _make_source(db, org_b.id, "slack", integration_id=integ_b.id)

        result = _find_matching_sources(db, "slack", {"team_id": ""})

        assert result == []

    def test_correct_team_id_returns_only_matching_org_source(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        integ_a = _make_slack_integration(db, org_a.id, team_id="Ta")
        integ_b = _make_slack_integration(db, org_b.id, team_id="Tb")
        source_a = _make_source(db, org_a.id, "slack", integration_id=integ_a.id)
        _make_source(db, org_b.id, "slack", integration_id=integ_b.id)

        result = _find_matching_sources(db, "slack", {"team_id": "Ta"})

        assert [s.id for s in result] == [source_a.id]


# ---------------------------------------------------------------------------
# Intercom -- discriminator: workspace_id (via Integration.config)
# ---------------------------------------------------------------------------


class TestIntercomTenancyGuard:
    def test_missing_workspace_id_returns_empty_not_cross_tenant_fanout(self, db):
        """A missing workspace_id in provider_context must never fall
        through to `return query.all()`, which would fan every org's
        active intercom FeedbackSource back to the caller -- a
        cross-tenant leak."""
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        integ_a = _make_intercom_integration(db, org_a.id, workspace_id="wa")
        integ_b = _make_intercom_integration(db, org_b.id, workspace_id="wb")
        _make_source(db, org_a.id, "intercom", integration_id=integ_a.id)
        _make_source(db, org_b.id, "intercom", integration_id=integ_b.id)

        result = _find_matching_sources(db, "intercom", {})

        assert result == []

    def test_empty_string_workspace_id_returns_empty_not_cross_tenant_fanout(self, db):
        """The Intercom OAuth callback stores workspace_id with a `""`
        default (integrations.py:1051), so `""` must be caught by the
        guard the same as `None` -- `not x`, never `is None`."""
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        integ_a = _make_intercom_integration(db, org_a.id, workspace_id="wa")
        integ_b = _make_intercom_integration(db, org_b.id, workspace_id="wb")
        _make_source(db, org_a.id, "intercom", integration_id=integ_a.id)
        _make_source(db, org_b.id, "intercom", integration_id=integ_b.id)

        result = _find_matching_sources(db, "intercom", {"workspace_id": ""})

        assert result == []

    def test_correct_workspace_id_returns_only_matching_org_source(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        integ_a = _make_intercom_integration(db, org_a.id, workspace_id="wa")
        integ_b = _make_intercom_integration(db, org_b.id, workspace_id="wb")
        source_a = _make_source(db, org_a.id, "intercom", integration_id=integ_a.id)
        _make_source(db, org_b.id, "intercom", integration_id=integ_b.id)

        result = _find_matching_sources(db, "intercom", {"workspace_id": "wa"})

        assert [s.id for s in result] == [source_a.id]


# ---------------------------------------------------------------------------
# Email -- discriminator: source_id (resolved directly by the webhook
# handler, matched against FeedbackSource.id)
# ---------------------------------------------------------------------------


class TestEmailTenancyGuard:
    def test_missing_source_id_returns_empty_not_cross_tenant_fanout(self, db):
        """A missing source_id in provider_context must never fall through
        to `return query.all()`, which would fan every org's active email
        FeedbackSource back to the caller -- a cross-tenant leak."""
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        _make_source(db, org_a.id, "email")
        _make_source(db, org_b.id, "email")

        result = _find_matching_sources(db, "email", {})

        assert result == []

    def test_empty_string_source_id_returns_empty_not_cross_tenant_fanout(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        _make_source(db, org_a.id, "email")
        _make_source(db, org_b.id, "email")

        result = _find_matching_sources(db, "email", {"source_id": ""})

        assert result == []

    def test_correct_source_id_returns_only_matching_org_source(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        source_a = _make_source(db, org_a.id, "email")
        _make_source(db, org_b.id, "email")

        result = _find_matching_sources(db, "email", {"source_id": source_a.id})

        assert [s.id for s in result] == [source_a.id]


# ---------------------------------------------------------------------------
# Webhook -- discriminator: source_id (matched against FeedbackSource.id)
# ---------------------------------------------------------------------------


class TestWebhookTenancyGuard:
    def test_missing_source_id_returns_empty_not_cross_tenant_fanout(self, db):
        """A missing source_id in provider_context must never fall through
        to `return query.all()`, which would fan every org's active
        webhook FeedbackSource back to the caller -- a cross-tenant
        leak."""
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        _make_source(db, org_a.id, "webhook")
        _make_source(db, org_b.id, "webhook")

        result = _find_matching_sources(db, "webhook", {})

        assert result == []

    def test_empty_string_source_id_returns_empty_not_cross_tenant_fanout(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        _make_source(db, org_a.id, "webhook")
        _make_source(db, org_b.id, "webhook")

        result = _find_matching_sources(db, "webhook", {"source_id": ""})

        assert result == []

    def test_correct_source_id_returns_only_matching_org_source(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        source_a = _make_source(db, org_a.id, "webhook")
        _make_source(db, org_b.id, "webhook")

        result = _find_matching_sources(db, "webhook", {"source_id": source_a.id})

        assert [s.id for s in result] == [source_a.id]


# ---------------------------------------------------------------------------
# Zendesk -- regression check only. This branch already guarded correctly
# (`if not subdomain: return []`) before Phase 2; it must be untouched.
# ---------------------------------------------------------------------------


class TestZendeskBranchUnchanged:
    def test_zendesk_branch_unchanged(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        _make_zendesk_integration(db, org_a.id, subdomain="orga")
        _make_zendesk_integration(db, org_b.id, subdomain="orgb")
        source_a = _make_source(db, org_a.id, "zendesk")
        _make_source(db, org_b.id, "zendesk")

        assert _find_matching_sources(db, "zendesk", {}) == []
        assert _find_matching_sources(db, "zendesk", {"subdomain": ""}) == []
        assert [s.id for s in _find_matching_sources(db, "zendesk", {"subdomain": "orga"})] == [
            source_a.id
        ]


# ---------------------------------------------------------------------------
# _process_event_for_source -- OAuth token decryption before fetch_context
# (worker decrypt mirrors: source_events.py:314 covers Slack AND Intercom --
# one decrypt, one path.)
# ---------------------------------------------------------------------------


class TestProcessEventForSourceDecrypt:
    """_process_event_for_source must hand adapter.fetch_context the PLAINTEXT
    token, never the ciphertext stored in integrations.oauth_access_token."""

    def _setup(self, db, source_type: str, token: str):
        org = _make_org(db, name=f"{source_type.title()} Context Co")
        integ = Integration(
            organization_id=org.id,
            type=source_type,
            config={"integration_type": "oauth"},
            oauth_access_token=token,
            is_active=True,
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)

        source = FeedbackSource(
            organization_id=org.id,
            integration_id=integ.id,
            source_type=source_type,
            is_active=True,
            auto_import=False,
            triggers={},
            field_mapping={"include_context": True},
            provider_config={"channel_id": "C123"} if source_type == "slack" else {},
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return org, integ, source

    def _adapter(self):
        adapter = MagicMock()
        adapter.check_triggers.return_value = True
        adapter.get_external_ids.return_value = ("ext-1", "msg-1")
        adapter.extract_content.return_value = {"text": "Billing is broken", "metadata": {}}
        adapter.fetch_context.return_value = {}
        return adapter

    def _call(self, db, source, adapter):
        from src.tasks.source_events import _process_event_for_source

        event_data = {"channel": "C123", "ts": "123.456"}
        return _process_event_for_source(
            db,
            source,
            adapter,
            "evt-1",
            "message",
            event_data,
        )

    def test_slack_path_decrypts_before_fetch_context(self, db):
        org, integ, source = self._setup(db, "slack", _encrypt("xoxb-slack-context"))
        assert "xoxb-slack-context" not in integ.oauth_access_token
        adapter = self._adapter()

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ENCRYPTION_KEY}):
            result = self._call(db, source, adapter)

        assert adapter.fetch_context.call_args.args[1] == "xoxb-slack-context"
        assert result["status"] == "pending_created"

    def test_intercom_path_decrypts_before_fetch_context(self, db):
        org, integ, source = self._setup(db, "intercom", _encrypt("intercom-context-token"))
        assert "intercom-context-token" not in integ.oauth_access_token
        adapter = self._adapter()

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ENCRYPTION_KEY}):
            result = self._call(db, source, adapter)

        assert adapter.fetch_context.call_args.args[1] == "intercom-context-token"
        assert result["status"] == "pending_created"

    def test_missing_key_records_error_without_fetching_context(self, db):
        org, integ, source = self._setup(db, "slack", _encrypt("xoxb-slack-context"))
        adapter = self._adapter()

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ""}):
            result = self._call(db, source, adapter)

        assert result == {"source_id": source.id, "status": "context_fetch_error"}
        adapter.fetch_context.assert_not_called()

    def test_corrupt_ciphertext_records_error_without_fetching_context(self, db):
        org, integ, source = self._setup(db, "slack", "garbage-not-fernet")
        adapter = self._adapter()

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ENCRYPTION_KEY}):
            result = self._call(db, source, adapter)

        assert result == {"source_id": source.id, "status": "context_fetch_error"}
        adapter.fetch_context.assert_not_called()
