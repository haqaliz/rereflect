"""Tenancy tests for the Intercom branch of _find_matching_sources.

This file guards the function that was the site of
`intercom-webhook-unauthenticated-cross-org-write` (P0, fixed on
feat/integration-auth-tenancy-hardening). Before that fix a payload with no
`app_id` fell through to a query filtered only by source_type + is_active,
matching every active Intercom source in EVERY organization on the instance.

This aspect widens the same function to a second credential source
(token-paste, `IntercomIntegration`) so that a token-paste-connected org can
actually ingest. Widening the site of a cross-tenant write is not a routine
edit, so the pre-existing guarantees are characterized here FIRST -- the tests
below that assert the OAuth behaviour and the missing/empty-workspace_id cases
were written to pass against the code as it stood, and must keep passing.

See docs/planning/intercom-selfhost-ingestion/tenancy-discriminator/.
"""
import sys
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.models import (
    FeedbackSource,
    Integration,
    IntercomIntegration,
    Organization,
)

WORKSPACE_A = "ws_org_a"
WORKSPACE_B = "ws_org_b"


# ──────────────────────────── Harness ─────────────────────────────────────────


def _make_org(db, name) -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_oauth_integration(db, org_id, workspace_id, is_active=True) -> Integration:
    integration = Integration(
        organization_id=org_id,
        type="intercom",
        name="Intercom (OAuth)",
        is_active=is_active,
        config={"workspace_id": workspace_id},
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def _make_token_integration(
    db, org_id, workspace_id, is_active=True
) -> IntercomIntegration:
    row = IntercomIntegration(
        organization_id=org_id,
        access_token="enc:blob",
        client_secret=None,
        workspace_id=workspace_id,
        is_active=is_active,
        connected_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_source(db, org_id, integration_id=None, is_active=True) -> FeedbackSource:
    source = FeedbackSource(
        organization_id=org_id,
        integration_id=integration_id,
        source_type="intercom",
        is_active=is_active,
        auto_import=True,
        triggers={"new_conversations": True},
        field_mapping={},
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _find(db, workspace_id):
    from src.tasks.source_events import _find_matching_sources

    return _find_matching_sources(db, "intercom", {"workspace_id": workspace_id})


# ─────────── Characterization: the P0 guarantees, written to pass ─────────────


class TestPreExistingGuarantees:
    """These describe behaviour that already holds. If the widening breaks any
    of them, it has reintroduced a cross-tenant defect."""

    def test_missing_workspace_id_returns_empty(self, db):
        """C3 — THE P0 guarantee. Must be checked before any lookup runs."""
        org = _make_org(db, "Org A")
        _make_oauth_integration(db, org.id, WORKSPACE_A)
        _make_source(db, org.id)

        from src.tasks.source_events import _find_matching_sources

        assert _find_matching_sources(db, "intercom", {}) == []
        assert _find_matching_sources(db, "intercom", {"workspace_id": None}) == []

    def test_empty_string_workspace_id_returns_empty(self, db):
        """C4 — "" is the OAuth callback's stored default, so the guard must be
        `not workspace_id`, never `is None`. Pinned so nobody 'tidies' it."""
        org = _make_org(db, "Org A")
        _make_oauth_integration(db, org.id, WORKSPACE_A)
        _make_source(db, org.id)

        assert _find(db, "") == []

    def test_unknown_workspace_id_returns_empty(self, db):
        """C5 — no fall-through to an unfiltered query."""
        org = _make_org(db, "Org A")
        _make_oauth_integration(db, org.id, WORKSPACE_A)
        _make_source(db, org.id)

        assert _find(db, "ws_nobody") == []

    def test_oauth_org_still_matches_its_own_source(self, db):
        """C2 — existing OAuth behaviour, unchanged."""
        org = _make_org(db, "Org A")
        integration = _make_oauth_integration(db, org.id, WORKSPACE_A)
        source = _make_source(db, org.id, integration_id=integration.id)

        assert [s.id for s in _find(db, WORKSPACE_A)] == [source.id]

    def test_inactive_oauth_integration_does_not_match(self, db):
        """C8"""
        org = _make_org(db, "Org A")
        integration = _make_oauth_integration(db, org.id, WORKSPACE_A, is_active=False)
        _make_source(db, org.id, integration_id=integration.id)

        assert _find(db, WORKSPACE_A) == []

    def test_inactive_source_does_not_match(self, db):
        org = _make_org(db, "Org A")
        integration = _make_oauth_integration(db, org.id, WORKSPACE_A)
        _make_source(db, org.id, integration_id=integration.id, is_active=False)

        assert _find(db, WORKSPACE_A) == []

    def test_other_branches_are_untouched(self, db):
        """C9 — the widening must not leak into slack/email/webhook/zendesk."""
        from src.tasks.source_events import _find_matching_sources

        assert _find_matching_sources(db, "slack", {}) == []
        assert _find_matching_sources(db, "slack", {"team_id": None}) == []
        assert _find_matching_sources(db, "email", {}) == []
        assert _find_matching_sources(db, "webhook", {}) == []
        assert _find_matching_sources(db, "zendesk", {}) == []


# ──────────────────── The widening: token-paste must resolve ──────────────────


class TestTokenPasteResolution:
    def test_token_paste_org_matches_its_source(self, db):
        """C1 — without this the whole token-paste path ingests nothing.

        Note the source has integration_id=None (token-paste is own-auth, like
        zendesk/jira), so it cannot be reached by the OAuth filter at all.
        """
        org = _make_org(db, "Org A")
        _make_token_integration(db, org.id, WORKSPACE_A)
        source = _make_source(db, org.id, integration_id=None)

        assert [s.id for s in _find(db, WORKSPACE_A)] == [source.id]

    def test_inactive_token_integration_does_not_match(self, db):
        """C7 — disconnect must actually stop ingestion."""
        org = _make_org(db, "Org A")
        _make_token_integration(db, org.id, WORKSPACE_A, is_active=False)
        _make_source(db, org.id, integration_id=None)

        assert _find(db, WORKSPACE_A) == []

    def test_token_paste_workspace_mismatch_does_not_match(self, db):
        org = _make_org(db, "Org A")
        _make_token_integration(db, org.id, WORKSPACE_A)
        _make_source(db, org.id, integration_id=None)

        assert _find(db, WORKSPACE_B) == []


# ──────────────────────── Cross-tenant, both paths ────────────────────────────


class TestCrossTenantIsolation:
    def test_token_paste_org_never_sees_another_orgs_source(self, db):
        """C6 — token-paste vs token-paste."""
        org_a = _make_org(db, "Org A")
        org_b = _make_org(db, "Org B")
        _make_token_integration(db, org_a.id, WORKSPACE_A)
        _make_token_integration(db, org_b.id, WORKSPACE_B)
        source_a = _make_source(db, org_a.id, integration_id=None)
        _make_source(db, org_b.id, integration_id=None)

        assert [s.id for s in _find(db, WORKSPACE_A)] == [source_a.id]

    def test_mixed_paths_do_not_leak_into_each_other(self, db):
        """C6 — the combination the `or_` introduces: org A on token-paste,
        org B on OAuth. Each must see only its own."""
        org_a = _make_org(db, "Org A")
        org_b = _make_org(db, "Org B")
        _make_token_integration(db, org_a.id, WORKSPACE_A)
        integration_b = _make_oauth_integration(db, org_b.id, WORKSPACE_B)
        source_a = _make_source(db, org_a.id, integration_id=None)
        source_b = _make_source(db, org_b.id, integration_id=integration_b.id)

        assert [s.id for s in _find(db, WORKSPACE_A)] == [source_a.id]
        assert [s.id for s in _find(db, WORKSPACE_B)] == [source_b.id]

    def test_oauth_org_unaffected_by_an_unrelated_token_paste_org(self, db):
        """The widening must not make an OAuth org's lookup return more."""
        org_a = _make_org(db, "Org A")
        org_b = _make_org(db, "Org B")
        integration_a = _make_oauth_integration(db, org_a.id, WORKSPACE_A)
        source_a = _make_source(db, org_a.id, integration_id=integration_a.id)
        _make_token_integration(db, org_b.id, WORKSPACE_B)
        _make_source(db, org_b.id, integration_id=None)

        assert [s.id for s in _find(db, WORKSPACE_A)] == [source_a.id]

    def test_two_orgs_sharing_one_workspace_both_match(self, db):
        """ACCEPTED, DOCUMENTED SEMANTICS -- not a defect.

        Two orgs on one instance that connect the SAME Intercom workspace both
        receive its events. This is pre-existing for the OAuth path and is
        exactly how Zendesk treats a shared subdomain. It is a property of
        workspace-keyed tenancy. Pinned here so the next reader does not
        'fix' it into a silent single-org drop.
        """
        org_a = _make_org(db, "Org A")
        org_b = _make_org(db, "Org B")
        _make_token_integration(db, org_a.id, WORKSPACE_A)
        _make_token_integration(db, org_b.id, WORKSPACE_A)
        source_a = _make_source(db, org_a.id, integration_id=None)
        source_b = _make_source(db, org_b.id, integration_id=None)

        matched = {s.id for s in _find(db, WORKSPACE_A)}
        assert matched == {source_a.id, source_b.id}


# ──────────────────────── End to end ──────────────────────────────────────────


def _patch_db_session(monkeypatch, db):
    import src.tasks.source_events as task_mod

    @contextmanager
    def fake_get_db():
        yield db

    monkeypatch.setattr(task_mod, "get_db_session", fake_get_db)


@pytest.fixture
def _no_op_side_effects(monkeypatch):
    import src.cache as cache_mod
    import src.tasks.analysis as analysis_mod

    monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", MagicMock())
    monkeypatch.setattr(cache_mod, "cache_invalidate", MagicMock())


class TestTokenPasteEndToEnd:
    def test_token_paste_org_ingests_a_feedback_item(
        self, db, monkeypatch, _no_op_side_effects
    ):
        """C10 — the query being right is necessary but not sufficient; this
        proves a token-paste-connected org actually ingests."""
        import json
        from pathlib import Path

        from src.models import FeedbackItem
        from src.tasks.source_events import process_source_event

        fixture = json.loads(
            (
                Path(__file__).parent / "fixtures" / "intercom_webhook_envelope.json"
            ).read_text()
        )

        org = _make_org(db, "Org A")
        _make_token_integration(db, org.id, fixture["app_id"])
        _make_source(db, org.id, integration_id=None)
        _patch_db_session(monkeypatch, db)

        process_source_event(
            source_type="intercom",
            external_event_id=fixture["data"]["item"]["id"],
            event_type=fixture["topic"],
            event_data=fixture,
            provider_context={
                "conversation_id": fixture["data"]["item"]["id"],
                "workspace_id": fixture["app_id"],
            },
        )

        items = db.query(FeedbackItem).all()
        assert len(items) == 1
        assert items[0].organization_id == org.id


# ──────────────────────── Model parity ────────────────────────────────────────


WRITEBACK_INTEGRATION_COLUMNS = (
    "writeback_enabled",
    "writeback_action",
    "last_writeback_at",
    "last_writeback_status",
    "last_writeback_error",
)
WRITEBACK_FEEDBACK_COLUMNS = ("intercom_writeback_at",)


class TestModelParity:
    def _import_backend_models(self):
        """Import backend IntercomIntegration + FeedbackItem via the sys.path
        swap. worker-service cannot import backend-api in production; the
        parity harness imports it for the test process only, then restores
        the module state.
        """
        import os

        worktree = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        backend_src = os.path.join(worktree, "services", "backend-api")

        saved_mods = {
            k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")
        }
        for k in saved_mods:
            del sys.modules[k]

        sys.path.insert(0, backend_src)
        try:
            from src.models.feedback import FeedbackItem as BackendFeedbackItem
            from src.models.intercom_integration import (
                IntercomIntegration as BackendIntercomIntegration,
            )

            return BackendIntercomIntegration, BackendFeedbackItem
        finally:
            sys.path.remove(backend_src)
            for k in list(sys.modules.keys()):
                if k == "src" or k.startswith("src."):
                    del sys.modules[k]
            sys.modules.update(saved_mods)

    def test_worker_and_backend_intercom_integration_columns_match(self):
        """The worker's no-FK mirror must match the backend model exactly.

        worker-service cannot import backend-api, so the model is duplicated.
        A drift here is silent: the worker would query a column the table has
        under a different name, or miss one entirely, and resolution would fail
        at runtime rather than in a test.

        Same sys.path/sys.modules swap technique as
        test_zendesk_adapter.py::TestModelsAndMigration.
        """
        from src.models import IntercomIntegration as WorkerModel

        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        BackendModel, _ = self._import_backend_models()
        backend_cols = {c.name for c in BackendModel.__table__.columns}

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )

    def test_worker_and_backend_feedback_item_columns_match(self):
        """The worker's no-FK FeedbackItem mirror must match the backend
        model exactly — same drift risk as the IntercomIntegration mirror."""
        from src.models import FeedbackItem as WorkerModel

        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        _, BackendFeedbackItem = self._import_backend_models()
        backend_cols = {c.name for c in BackendFeedbackItem.__table__.columns}

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )

    def test_writeback_column_types_match(self):
        """The worker mirror must match the backend column TYPES, not just
        names (spec AC4 "including types").

        Catches DateTime(timezone=True) drift (timestamptz vs naive) and
        String(64) vs String(50) slips — both silent at runtime: the worker
        would write/read the columns with the wrong type and resolution
        would misbehave on real data.
        """
        from src.models import FeedbackItem as WorkerFeedbackItem
        from src.models import IntercomIntegration as WorkerIntercomIntegration

        BackendIntercomIntegration, BackendFeedbackItem = self._import_backend_models()

        worker_models = {
            "intercom_integrations": WorkerIntercomIntegration,
            "feedback_items": WorkerFeedbackItem,
        }
        backend_models = {
            "intercom_integrations": BackendIntercomIntegration,
            "feedback_items": BackendFeedbackItem,
        }
        shared_columns = {
            "intercom_integrations": WRITEBACK_INTEGRATION_COLUMNS,
            "feedback_items": WRITEBACK_FEEDBACK_COLUMNS,
        }

        for table, names in shared_columns.items():
            worker_table = worker_models[table].__table__
            backend_table = backend_models[table].__table__
            for name in names:
                worker_type = worker_table.columns[name].type
                backend_type = backend_table.columns[name].type
                # TypeEngine.__eq__ is identity-based in SQLAlchemy 2.0.32,
                # so compare _static_cache_key — the structural identity
                # SQLAlchemy itself uses for type comparison (class + params,
                # so String(64) vs String(50) and DateTime(timezone=True) vs
                # naive DateTime drift are both caught).
                assert (
                    worker_type._static_cache_key == backend_type._static_cache_key
                ), (
                    f"Type mismatch on {table}.{name}: "
                    f"worker {worker_type!r} != backend {backend_type!r}"
                )
