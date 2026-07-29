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

from datetime import datetime

import pytest

from src.models import Organization, FeedbackSource, Integration, ZendeskIntegration


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
