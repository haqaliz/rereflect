"""
TDD tests for zendesk_sync tasks and _sync_org core (ingestion-pull aspect).

Phase 1 (worker ZendeskIntegration model + column parity) was already
delivered by the ingestion-core aspect — see
tests/test_zendesk_adapter.py::TestModelsAndMigration. Not duplicated here.

Strategy: real SQLite (`db` fixture from conftest.py, real Base.metadata
tables), a fake ZendeskClient (MagicMock), and the REAL
`src.tasks.source_events._find_matching_sources` /
`_process_event_for_source` / `get_adapter("zendesk")` — no stubbing of the
shared ingestion core (per plan §1a/§1b, this is the executable spec for the
cross-aspect contract, in particular the dedup-on-rerun acceptance
criterion).
"""

from __future__ import annotations

import importlib
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.models import FeedbackItem, FeedbackSource, FeedbackSourceEvent, Organization, ZendeskIntegration


# ---------------------------------------------------------------------------
# Helpers (mirror tests/test_zendesk_adapter.py's fixtures)
# ---------------------------------------------------------------------------


def _make_org(db, name="Acme Co") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_zendesk_integration(
    db,
    org_id,
    subdomain="acmeco",
    is_active=True,
    last_synced_at=None,
    connected_at=None,
) -> ZendeskIntegration:
    integ = ZendeskIntegration(
        organization_id=org_id,
        subdomain=subdomain,
        email="agent@acmeco.com",
        api_token="enc:blob",
        is_active=is_active,
        connected_at=connected_at or datetime.utcnow(),
        last_synced_at=last_synced_at,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _make_zendesk_source(db, org_id, is_active=True) -> FeedbackSource:
    source = FeedbackSource(
        organization_id=org_id,
        source_type="zendesk",
        is_active=is_active,
        auto_import=True,
        triggers={"new_ticket": True},
        field_mapping={},
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _make_ticket(id, subject="Cannot login", description="<p>Getting a 500</p>",
                  requester_id=10, requester_email="sam@customer.com", status="open",
                  tags=None):
    return {
        "id": id,
        "subject": subject,
        "description": description,
        "status": status,
        "tags": tags or [],
        "requester_id": requester_id,
        "requester_email": requester_email,
    }


def _make_fake_client(tickets=None, end_time=1700000100):
    client = MagicMock()
    client.incremental_tickets.return_value = {
        "tickets": tickets if tickets is not None else [],
        "end_time": end_time,
    }
    return client


@pytest.fixture
def _no_analysis_delay(monkeypatch):
    """Neutralize analyze_single_feedback.delay so tests don't need a broker."""
    import src.tasks.analysis as analysis_mod
    monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", MagicMock())


# ---------------------------------------------------------------------------
# Phase 3: TestSyncOrgCore
# ---------------------------------------------------------------------------


class TestSyncOrgCore:
    def test_creates_one_feedback_item_per_new_ticket(self, db, _no_analysis_delay):
        import src.tasks.zendesk_sync as zs

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id)

        tickets = [
            _make_ticket(1, requester_email="a@example.com"),
            _make_ticket(2, requester_email="b@example.com"),
            _make_ticket(3, requester_email="c@example.com"),
        ]
        client = _make_fake_client(tickets=tickets)

        result = zs._sync_org(org.id, db, client, integ)

        items = db.query(FeedbackItem).all()
        assert len(items) == 3
        by_ext_id = {i.source_external_id: i for i in items}
        assert set(by_ext_id.keys()) == {"1", "2", "3"}
        for i in items:
            assert i.source == "zendesk"
        assert by_ext_id["1"].customer_email == "a@example.com"
        assert result["tickets_ingested"] == 3
        assert result["tickets_seen"] == 3

    def test_rerun_same_tickets_creates_no_duplicates(self, db, _no_analysis_delay):
        import src.tasks.zendesk_sync as zs

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id)

        tickets = [_make_ticket(555, requester_email="sam@customer.com")]
        client = _make_fake_client(tickets=tickets)

        zs._sync_org(org.id, db, client, integ)
        zs._sync_org(org.id, db, client, integ)

        items = db.query(FeedbackItem).all()
        assert len(items) == 1

        events = db.query(FeedbackSourceEvent).filter(
            FeedbackSourceEvent.status == "processed"
        ).all()
        assert len(events) == 1
        assert events[0].external_message_id == "555"

    def test_cursor_advances_to_response_end_time_and_persists(self, db, _no_analysis_delay):
        import src.tasks.zendesk_sync as zs

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id)

        client = _make_fake_client(tickets=[_make_ticket(1)], end_time=1700000555)

        zs._sync_org(org.id, db, client, integ)

        assert integ.last_synced_at == datetime.utcfromtimestamp(1700000555)

    def test_first_run_uses_connected_at_when_last_synced_at_null(self, db, _no_analysis_delay):
        import src.tasks.zendesk_sync as zs

        org = _make_org(db)
        connected_at = datetime(2026, 6, 1, 12, 0, 0)
        integ = _make_zendesk_integration(
            db, org.id, subdomain="acmeco", last_synced_at=None, connected_at=connected_at,
        )
        _make_zendesk_source(db, org.id)

        client = _make_fake_client(tickets=[])

        zs._sync_org(org.id, db, client, integ)

        # Naive UTC datetime -> unix ts, same conversion the implementation
        # uses, so this assertion is deterministic regardless of the
        # runner's local timezone.
        from datetime import timezone
        expected_start = int(connected_at.replace(tzinfo=timezone.utc).timestamp())

        call = client.incremental_tickets.call_args
        start_time = call.kwargs.get("start_time") if call.kwargs else call.args[0]
        assert start_time == expected_start

    def test_missing_requester_email_ingests_with_null_customer_email(self, db, _no_analysis_delay):
        import src.tasks.zendesk_sync as zs

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id)

        ticket = _make_ticket(42, requester_id=None, requester_email=None)
        client = _make_fake_client(tickets=[ticket])

        zs._sync_org(org.id, db, client, integ)

        items = db.query(FeedbackItem).all()
        assert len(items) == 1
        assert items[0].customer_email is None

    def test_unmatched_subdomain_or_no_source_is_logged_noop(self, db, _no_analysis_delay):
        import src.tasks.zendesk_sync as zs

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, subdomain="acmeco")
        # No FeedbackSource created for this org at all.

        client = _make_fake_client(tickets=[_make_ticket(1)])

        result = zs._sync_org(org.id, db, client, integ)

        assert result["no_source_match"] is True
        assert result["tickets_ingested"] == 0
        assert result["tickets_seen"] == 1
        assert db.query(FeedbackItem).count() == 0

    def test_analysis_queued_for_each_created_item(self, db, monkeypatch):
        import src.tasks.zendesk_sync as zs
        import src.tasks.analysis as analysis_mod

        mock_delay = MagicMock()
        monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", mock_delay)

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id)

        tickets = [_make_ticket(1), _make_ticket(2)]
        client = _make_fake_client(tickets=tickets)

        zs._sync_org(org.id, db, client, integ)

        assert mock_delay.call_count == 2


# ---------------------------------------------------------------------------
# Phase 4: TestSyncZendeskOrgBody
# ---------------------------------------------------------------------------


class TestSyncZendeskOrgBody:
    def test_not_found(self, db):
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)

        from contextlib import contextmanager

        @contextmanager
        def fake_get_db():
            yield db

        with patch.object(zs, "get_db_session", fake_get_db):
            task_self = MagicMock()
            result = zs._sync_zendesk_org_body(task_self, 999999)

        assert result["status"] == "not_found"

    def test_inactive_skipped(self, db):
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)

        from contextlib import contextmanager

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, is_active=False)

        @contextmanager
        def fake_get_db():
            yield db

        with patch.object(zs, "get_db_session", fake_get_db):
            task_self = MagicMock()
            result = zs._sync_zendesk_org_body(task_self, integ.id)

        assert result["status"] == "inactive"

    def test_missing_encryption_key_returns_error_no_retry(self, db):
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)

        from contextlib import contextmanager

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)

        @contextmanager
        def fake_get_db():
            yield db

        with patch.object(zs, "get_db_session", fake_get_db), \
             patch.object(zs, "_decrypt", side_effect=ValueError("LLM_ENCRYPTION_KEY is not set")):
            task_self = MagicMock()
            result = zs._sync_zendesk_org_body(task_self, integ.id)

        assert result == {"status": "error", "reason": "missing_encryption_key"}
        db.refresh(integ)
        assert integ.last_sync_status == "error"
        task_self.retry.assert_not_called()

    def test_auth_failure_sets_last_error_without_raising(self, db):
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)

        from contextlib import contextmanager

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)

        @contextmanager
        def fake_get_db():
            yield db

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.incremental_tickets.side_effect = zs.ZendeskAuthError("bad token")

        with patch.object(zs, "get_db_session", fake_get_db), \
             patch.object(zs, "_decrypt", return_value="plain-token"), \
             patch.object(zs, "ZendeskClient", return_value=mock_client_instance):
            task_self = MagicMock()
            result = zs._sync_zendesk_org_body(task_self, integ.id)

        assert result["status"] == "error"
        db.refresh(integ)
        assert integ.last_sync_status == "error"
        assert integ.last_error is not None
        assert integ.is_active is True  # NOT disconnected — operator-recoverable
        task_self.retry.assert_not_called()

    def test_transient_error_retries(self, db):
        from celery.exceptions import Retry
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)

        from contextlib import contextmanager

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id)

        @contextmanager
        def fake_get_db():
            yield db

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.incremental_tickets.side_effect = zs.ZendeskTransientError("rate limited")

        task_self = MagicMock()
        task_self.retry.side_effect = Retry()

        with patch.object(zs, "get_db_session", fake_get_db), \
             patch.object(zs, "_decrypt", return_value="plain-token"), \
             patch.object(zs, "ZendeskClient", return_value=mock_client_instance):
            with pytest.raises(Retry):
                zs._sync_zendesk_org_body(task_self, integ.id)

        task_self.retry.assert_called_once()

    def test_no_source_match_records_status_without_raising(self, db, monkeypatch):
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)
        import src.tasks.analysis as analysis_mod
        monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", MagicMock())

        from contextlib import contextmanager

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, subdomain="acmeco")
        # No FeedbackSource for this org.

        @contextmanager
        def fake_get_db():
            yield db

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.incremental_tickets.return_value = {
            "tickets": [_make_ticket(1)],
            "end_time": 1700000100,
        }

        with patch.object(zs, "get_db_session", fake_get_db), \
             patch.object(zs, "_decrypt", return_value="plain-token"), \
             patch.object(zs, "ZendeskClient", return_value=mock_client_instance):
            task_self = MagicMock()
            result = zs._sync_zendesk_org_body(task_self, integ.id)

        assert result["status"] == "success"
        db.refresh(integ)
        assert integ.last_sync_status == "no_source"
        assert integ.last_error is not None
        task_self.retry.assert_not_called()

    def test_success_updates_last_synced_at_and_status(self, db, monkeypatch):
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)
        import src.tasks.analysis as analysis_mod
        monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", MagicMock())

        from contextlib import contextmanager

        org = _make_org(db)
        integ = _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id)

        @contextmanager
        def fake_get_db():
            yield db

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.incremental_tickets.return_value = {
            "tickets": [_make_ticket(1)],
            "end_time": 1700000100,
        }

        with patch.object(zs, "get_db_session", fake_get_db), \
             patch.object(zs, "_decrypt", return_value="plain-token"), \
             patch.object(zs, "ZendeskClient", return_value=mock_client_instance):
            task_self = MagicMock()
            result = zs._sync_zendesk_org_body(task_self, integ.id)

        assert result["status"] == "success"
        db.refresh(integ)
        assert integ.last_sync_status == "success"
        assert integ.last_error is None
        assert integ.last_synced_at == datetime.utcfromtimestamp(1700000100)


# ---------------------------------------------------------------------------
# Phase 4b: TestFanOutTask
# ---------------------------------------------------------------------------


class TestFanOutTask:
    def test_fanout_enqueues_active_integrations_only(self, db):
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)

        from contextlib import contextmanager

        org = _make_org(db)
        active = _make_zendesk_integration(db, org.id, subdomain="acmeco", is_active=True)
        org2 = _make_org(db, name="Other Co")
        _make_zendesk_integration(db, org2.id, subdomain="otherco", is_active=False)

        @contextmanager
        def fake_get_db():
            yield db

        with patch.object(zs, "get_db_session", fake_get_db), \
             patch.object(zs, "sync_zendesk_org") as mock_task:
            mock_task.delay = MagicMock()
            zs.sync_all_zendesk()

        mock_task.delay.assert_called_once_with(active.id)

    def test_fanout_no_active_integrations_returns_zero(self, db):
        import src.tasks.zendesk_sync as zs
        importlib.reload(zs)

        from contextlib import contextmanager

        @contextmanager
        def fake_get_db():
            yield db

        with patch.object(zs, "get_db_session", fake_get_db), \
             patch.object(zs, "sync_zendesk_org") as mock_task:
            mock_task.delay = MagicMock()
            result = zs.sync_all_zendesk()

        assert result["status"] == "no_integrations"
        assert result["queued"] == 0


# ---------------------------------------------------------------------------
# Phase 5: TestCeleryTaskRegistration
# ---------------------------------------------------------------------------


class TestCeleryTaskRegistration:
    def test_sync_all_zendesk_is_registered(self):
        from src.celery_app import celery_app
        assert "src.tasks.zendesk_sync.sync_all_zendesk" in celery_app.tasks

    def test_sync_zendesk_org_is_registered(self):
        from src.celery_app import celery_app
        assert "src.tasks.zendesk_sync.sync_zendesk_org" in celery_app.tasks

    def test_beat_schedule_has_zendesk_entry(self):
        from src.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "sync-zendesk-every-15-min" in schedule
        entry = schedule["sync-zendesk-every-15-min"]
        assert entry["schedule"] == 900.0


# ---------------------------------------------------------------------------
# Phase 7: full-run acceptance sweep
#
# One consolidated end-to-end regression harness replaying the spec's
# acceptance criteria list (ingestion-pull/spec.md) against the finished
# module — not new behavior, a final cross-check that Phases 1-6 compose
# correctly.
# ---------------------------------------------------------------------------


class TestFullRunAcceptanceSweep:
    def test_end_to_end_multi_page_dedup_cursor_and_first_run_fallback(
        self, db, monkeypatch
    ):
        import src.tasks.zendesk_sync as zs
        import src.tasks.analysis as analysis_mod
        from datetime import timezone

        monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", MagicMock())

        org = _make_org(db)
        connected_at = datetime(2026, 6, 1, 0, 0, 0)
        # D1: freshly-connected integration, no prior last_synced_at.
        integ = _make_zendesk_integration(
            db, org.id, subdomain="acmeco", last_synced_at=None, connected_at=connected_at,
        )
        _make_zendesk_source(db, org.id)

        # Multi-page response: page 1 has a next_page (client already
        # resolved pagination internally — _sync_org only sees the final
        # merged result), page 2 is end_of_stream.
        tickets = [
            _make_ticket(101, requester_email="alice@customer.com"),
            _make_ticket(102, requester_email="bob@customer.com"),
        ]
        client = _make_fake_client(tickets=tickets, end_time=1700005000)

        # --- First run: acceptance criterion "first run ingests only
        # tickets at/after connection time" -> assert connected_at (not
        # epoch/None) was the effective starting cursor.
        result1 = zs._sync_org(org.id, db, client, integ)

        expected_start = int(connected_at.replace(tzinfo=timezone.utc).timestamp())
        call = client.incremental_tickets.call_args
        start_time = call.kwargs.get("start_time") if call.kwargs else call.args[0]
        assert start_time == expected_start

        items = db.query(FeedbackItem).all()
        assert len(items) == 2
        assert {i.source_external_id for i in items} == {"101", "102"}
        assert result1["tickets_ingested"] == 2

        # Cursor persisted to the response's end_time.
        assert integ.last_synced_at == datetime.utcfromtimestamp(1700005000)

        # --- Immediate re-run with the SAME cursor/tickets (simulating a
        # pull-cursor overlap): no duplicates via FeedbackSourceEvent dedup.
        result2 = zs._sync_org(org.id, db, client, integ)

        items_after_rerun = db.query(FeedbackItem).all()
        assert len(items_after_rerun) == 2  # unchanged
        assert result2["tickets_ingested"] == 0  # both deduped

        processed_events = db.query(FeedbackSourceEvent).filter(
            FeedbackSourceEvent.status == "processed"
        ).all()
        assert len(processed_events) == 2
        assert {e.external_message_id for e in processed_events} == {"101", "102"}

        # Final last_sync_status/last_error state via the task-wrapper body.
        from contextlib import contextmanager

        @contextmanager
        def fake_get_db():
            yield db

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.incremental_tickets.return_value = {
            "tickets": [],
            "end_time": 1700005000,
        }

        with patch.object(zs, "get_db_session", fake_get_db), \
             patch.object(zs, "_decrypt", return_value="plain-token"), \
             patch.object(zs, "ZendeskClient", return_value=mock_client_instance):
            task_self = MagicMock()
            body_result = zs._sync_zendesk_org_body(task_self, integ.id)

        assert body_result["status"] == "success"
        db.refresh(integ)
        assert integ.last_sync_status == "success"
        assert integ.last_error is None
