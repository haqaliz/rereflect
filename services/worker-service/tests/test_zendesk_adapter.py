"""Tests for Zendesk adapter (ingestion-core aspect)."""

import sys
from contextlib import contextmanager
from datetime import datetime

import pytest
from unittest.mock import patch, MagicMock

from src.adapters.zendesk import ZendeskAdapter
from src.models import Organization, FeedbackSource, ZendeskIntegration


@pytest.fixture
def adapter():
    return ZendeskAdapter()


class TestCheckTriggers:
    def test_new_ticket_trigger_matches_created_event(self, adapter):
        result = adapter.check_triggers(
            "ticket.created",
            {"ticket": {"id": 1, "subject": "Hi"}, "subdomain": "acmeco"},
            {"new_ticket": True},
        )
        assert result == "new_ticket"

    def test_new_ticket_trigger_does_not_match_other_event(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {"ticket": {"id": 1, "subject": "Hi"}, "subdomain": "acmeco"},
            {"new_ticket": True},
        )
        assert result is None

    def test_no_triggers_returns_none(self, adapter):
        result = adapter.check_triggers(
            "ticket.created",
            {"ticket": {"id": 1, "subject": "Hi"}, "subdomain": "acmeco"},
            {},
        )
        assert result is None

    def test_keyword_trigger_matches_subject(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {"ticket": {"id": 1, "subject": "Billing question"}, "subdomain": "acmeco"},
            {"keywords": ["billing"]},
        )
        assert result == "keyword:billing"

    def test_keyword_trigger_matches_description(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {
                "ticket": {
                    "id": 1,
                    "subject": "Hi",
                    "description": "<p>I have a billing question</p>",
                },
                "subdomain": "acmeco",
            },
            {"keywords": ["billing"]},
        )
        assert result == "keyword:billing"

    def test_keyword_trigger_case_insensitive(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {"ticket": {"id": 1, "subject": "BILLING issue"}, "subdomain": "acmeco"},
            {"keywords": ["billing"]},
        )
        assert result == "keyword:billing"

    def test_keyword_trigger_no_match_returns_none(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {"ticket": {"id": 1, "subject": "Hello there"}, "subdomain": "acmeco"},
            {"keywords": ["billing"]},
        )
        assert result is None

    def test_new_ticket_and_keyword_both_configured_new_ticket_wins(self, adapter):
        result = adapter.check_triggers(
            "ticket.created",
            {"ticket": {"id": 1, "subject": "Billing issue"}, "subdomain": "acmeco"},
            {"new_ticket": True, "keywords": ["billing"]},
        )
        assert result == "new_ticket"


class TestGetExternalIds:
    def test_returns_ticket_id_as_both_ids(self, adapter):
        event_data = {"ticket": {"id": 4521, "subject": "Billing issue"}, "subdomain": "acmeco"}
        event_id, message_id = adapter.get_external_ids(event_data)
        assert event_id == "4521"
        assert message_id == "4521"
        assert isinstance(event_id, str)
        assert isinstance(message_id, str)


class TestExtractContent:
    def test_builds_text_from_subject_and_description(self, adapter):
        event_data = {
            "ticket": {
                "id": 4521,
                "subject": "Billing issue",
                "description": "<p>My invoice is wrong</p>",
                "status": "open",
                "tags": ["billing", "urgent"],
                "requester_email": "jane@example.com",
            },
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == "Billing issue\n\nMy invoice is wrong"
        assert result["metadata"] == {
            "subdomain": "acmeco",
            "ticket_id": 4521,
            "status": "open",
            "requester_email": "jane@example.com",
            "tags": ["billing", "urgent"],
        }
        assert result["customer_email"] == "jane@example.com"

    def test_strips_html_from_subject_too(self, adapter):
        event_data = {
            "ticket": {
                "id": 1,
                "subject": "<b>Urgent</b>: cannot login",
                "description": "help",
            },
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert "<" not in result["text"]

    def test_handles_missing_description(self, adapter):
        event_data = {
            "ticket": {"id": 1, "subject": "Billing issue"},
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == "Billing issue"

    def test_handles_empty_string_description(self, adapter):
        event_data = {
            "ticket": {"id": 1, "subject": "Billing issue", "description": ""},
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == "Billing issue"

    def test_handles_missing_requester_email(self, adapter):
        event_data = {
            "ticket": {"id": 1, "subject": "Billing issue", "description": "help"},
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["metadata"]["requester_email"] is None
        assert result.get("customer_email") is None

    def test_handles_missing_tags(self, adapter):
        event_data = {
            "ticket": {"id": 1, "subject": "Billing issue", "description": "help"},
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["metadata"]["tags"] == []


class TestFetchContext:
    def test_returns_empty_without_access_token(self, adapter):
        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, None, {})
        assert result == {}

    def test_returns_empty_on_malformed_access_token(self, adapter):
        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, "no-colon-here", {})
        assert result == {}

    @patch("src.adapters.zendesk.httpx.Client")
    def test_fetches_ticket_and_requester_details(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        ticket_response = MagicMock()
        ticket_response.json.return_value = {"ticket": {"id": 4521, "requester_id": 999}}

        user_response = MagicMock()
        user_response.json.return_value = {
            "user": {"id": 999, "name": "Jane Doe", "email": "jane@example.com"}
        }

        mock_client.get.side_effect = [ticket_response, user_response]

        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, "agent@acmeco.com:apitoken123", {})

        first_call = mock_client.get.call_args_list[0]
        second_call = mock_client.get.call_args_list[1]
        assert first_call.args[0] == "https://acmeco.zendesk.com/api/v2/tickets/4521"
        assert second_call.args[0] == "https://acmeco.zendesk.com/api/v2/users/999"

        mock_client_cls.assert_called_once_with(
            timeout=10, auth=("agent@acmeco.com/token", "apitoken123")
        )

        assert result["requester_name"] == "Jane Doe"
        assert result["requester_email"] == "jane@example.com"
        assert result["ticket_url"] == "https://acmeco.zendesk.com/agent/tickets/4521"

    @patch("src.adapters.zendesk.httpx.Client")
    def test_skips_requester_fetch_when_no_requester_id(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        ticket_response = MagicMock()
        ticket_response.json.return_value = {"ticket": {"id": 4521}}
        mock_client.get.side_effect = [ticket_response]

        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, "agent@acmeco.com:apitoken123", {})

        assert mock_client.get.call_count == 1
        assert result["ticket_url"] == "https://acmeco.zendesk.com/agent/tickets/4521"
        assert "requester_name" not in result
        assert "requester_email" not in result

    @patch("src.adapters.zendesk.httpx.Client")
    def test_handles_api_error_gracefully(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("API error")

        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, "agent@acmeco.com:apitoken123", {})
        assert result == {}

    @pytest.mark.parametrize(
        "malicious_subdomain",
        [
            "evil.com#",
            "evil.com/",
            "a.b",
            "foo@bar",
            "",
            "foo_bar",
            "-lead",
            "trail-",
            "a" * 64,
        ],
    )
    @patch("src.adapters.zendesk.httpx.Client")
    def test_rejects_malicious_subdomain_without_sending_request(
        self, mock_client_cls, adapter, malicious_subdomain
    ):
        """SSRF guard: fetch_context must re-validate subdomain as a bare DNS
        label before ever constructing a URL/httpx.Client — mirrors
        ZendeskClient._assert_safe_subdomain in backend-api. A crafted
        subdomain containing '@', '#', '/', '.', or an oversized label must
        not reach the network layer (would otherwise let an attacker redirect
        the request host and exfiltrate the stored API token via auth=).
        """
        event_data = {"ticket": {"id": 4521}, "subdomain": malicious_subdomain}
        result = adapter.fetch_context(event_data, "agent@acmeco.com:apitoken123", {})
        assert result == {}
        mock_client_cls.assert_not_called()


class TestAdapterRegistry:
    def test_get_adapter_returns_zendesk_adapter(self):
        from src.adapters import get_adapter

        adapter = get_adapter("zendesk")
        assert isinstance(adapter, ZendeskAdapter)


class TestModelsAndMigration:
    def test_worker_and_backend_zendesk_integration_columns_match(self):
        """Worker ZendeskIntegration mirror columns must exactly match
        backend-api model columns (ingestion-core aspect).

        Same sys.path/sys.modules swap technique as
        test_salesforce_sync.py::TestModelsAndMigration.
        """
        import os

        from src.models import ZendeskIntegration as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        worktree = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        backend_src = os.path.join(worktree, "services", "backend-api")

        saved_mods = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
        for k in saved_mods:
            del sys.modules[k]

        sys.path.insert(0, backend_src)
        try:
            from src.models.zendesk_integration import ZendeskIntegration as BackendModel
            backend_cols = {c.name for c in BackendModel.__table__.columns}
        finally:
            sys.path.remove(backend_src)
            for k in list(sys.modules.keys()):
                if k == "src" or k.startswith("src."):
                    del sys.modules[k]
            sys.modules.update(saved_mods)

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )

    def test_worker_and_backend_feedback_zendesk_sync_columns_match(self):
        """Worker FeedbackZendeskSync mirror columns must exactly match
        backend-api model columns (reconcile-core-and-model aspect).

        Same sys.path/sys.modules swap technique as
        test_worker_and_backend_zendesk_integration_columns_match above.
        """
        import os

        from src.models import FeedbackZendeskSync as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        worktree = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        backend_src = os.path.join(worktree, "services", "backend-api")

        saved_mods = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
        for k in saved_mods:
            del sys.modules[k]

        sys.path.insert(0, backend_src)
        try:
            from src.models.feedback_zendesk_sync import FeedbackZendeskSync as BackendModel
            backend_cols = {c.name for c in BackendModel.__table__.columns}
        finally:
            sys.path.remove(backend_src)
            for k in list(sys.modules.keys()):
                if k == "src" or k.startswith("src."):
                    del sys.modules[k]
            sys.modules.update(saved_mods)

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )


# ---------------------------------------------------------------------------
# TestFindMatchingSources — zendesk subdomain matching branch
# ---------------------------------------------------------------------------


def _make_org(db, name="Acme Co") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


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


class TestFindMatchingSources:
    def test_matches_active_integration_and_active_source(self, db):
        from src.tasks.source_events import _find_matching_sources

        org = _make_org(db)
        _make_zendesk_integration(db, org.id, subdomain="acmeco")
        source = _make_zendesk_source(db, org.id)

        result = _find_matching_sources(db, "zendesk", {"subdomain": "acmeco"})

        assert [s.id for s in result] == [source.id]

    def test_inactive_integration_yields_no_match(self, db):
        from src.tasks.source_events import _find_matching_sources

        org = _make_org(db)
        _make_zendesk_integration(db, org.id, subdomain="acmeco", is_active=False)
        _make_zendesk_source(db, org.id)

        result = _find_matching_sources(db, "zendesk", {"subdomain": "acmeco"})

        assert result == []

    def test_no_integration_row_yields_no_match_no_exception(self, db):
        from src.tasks.source_events import _find_matching_sources

        org = _make_org(db)
        _make_zendesk_source(db, org.id)

        result = _find_matching_sources(db, "zendesk", {"subdomain": "unknown-subdomain"})

        assert result == []

    def test_only_matching_org_returned_when_two_orgs_exist(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        _make_zendesk_integration(db, org_a.id, subdomain="orga")
        _make_zendesk_integration(db, org_b.id, subdomain="orgb")
        source_a = _make_zendesk_source(db, org_a.id)
        _make_zendesk_source(db, org_b.id)

        result = _find_matching_sources(db, "zendesk", {"subdomain": "orga"})

        assert [s.id for s in result] == [source_a.id]

    def test_inactive_feedback_source_still_excluded(self, db):
        from src.tasks.source_events import _find_matching_sources

        org = _make_org(db)
        _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id, is_active=False)

        result = _find_matching_sources(db, "zendesk", {"subdomain": "acmeco"})

        assert result == []

    def test_missing_subdomain_returns_empty_not_cross_tenant_fanout(self, db):
        """A missing/empty subdomain in provider_context must never fall through
        to `return query.all()`, which would fan every org's active zendesk
        FeedbackSource back to the caller — a cross-tenant leak."""
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        _make_zendesk_integration(db, org_a.id, subdomain="orga")
        _make_zendesk_integration(db, org_b.id, subdomain="orgb")
        _make_zendesk_source(db, org_a.id)
        _make_zendesk_source(db, org_b.id)

        result = _find_matching_sources(db, "zendesk", {})

        assert result == []

    def test_empty_string_subdomain_returns_empty_not_cross_tenant_fanout(self, db):
        from src.tasks.source_events import _find_matching_sources

        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        _make_zendesk_integration(db, org_a.id, subdomain="orga")
        _make_zendesk_integration(db, org_b.id, subdomain="orgb")
        _make_zendesk_source(db, org_a.id)
        _make_zendesk_source(db, org_b.id)

        result = _find_matching_sources(db, "zendesk", {"subdomain": ""})

        assert result == []


# ---------------------------------------------------------------------------
# TestIngestionCoreIntegration — end-to-end process_source_event
# ---------------------------------------------------------------------------


def _patch_db_session(monkeypatch, db):
    """Patch get_db_session in the source_events task module to yield the test db."""
    import src.tasks.source_events as task_mod

    @contextmanager
    def fake_get_db():
        yield db

    monkeypatch.setattr(task_mod, "get_db_session", fake_get_db)


@pytest.fixture
def _no_op_side_effects(monkeypatch):
    """Neutralize the Celery/Redis side effects process_source_event triggers
    on the auto_import=True path so tests can run without a broker."""
    import src.tasks.analysis as analysis_mod
    import src.cache as cache_mod

    monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", MagicMock())
    monkeypatch.setattr(cache_mod, "cache_invalidate", MagicMock())


class TestIngestionCoreIntegration:
    def test_creates_exactly_one_feedback_item_and_sets_customer_email(
        self, db, monkeypatch, _no_op_side_effects
    ):
        from src.tasks.source_events import process_source_event
        from src.models import FeedbackItem

        org = _make_org(db)
        _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        process_source_event(
            source_type="zendesk",
            external_event_id="evt-555-a",
            event_type="ticket.created",
            event_data={
                "ticket": {
                    "id": 555,
                    "subject": "Cannot login",
                    "description": "<p>Getting a 500 error</p>",
                    "status": "open",
                    "tags": ["auth"],
                    "requester_email": "sam@customer.com",
                },
                "subdomain": "acmeco",
            },
            provider_context={"subdomain": "acmeco"},
        )

        items = db.query(FeedbackItem).all()
        assert len(items) == 1
        item = items[0]
        assert item.source == "zendesk"
        assert item.source_external_id == "555"
        assert item.customer_email == "sam@customer.com"
        assert item.text == "Cannot login\n\nGetting a 500 error"
        assert item.source_metadata["ticket_id"] == 555
        assert item.source_metadata["tags"] == ["auth"]

    def test_duplicate_event_is_deduped_via_feedback_source_event(
        self, db, monkeypatch, _no_op_side_effects
    ):
        """Reproduces + pins the fix for the pre-existing _log_event bug:
        _process_event_for_source computes the correct dedup key via
        adapter.get_external_ids() (ticket id, for Zendesk), but _log_event
        independently re-derives external_message_id via a Slack/webhook-
        shaped heuristic (event_data.get("ts") / .get("item", {}).get("ts")
        / .get("content_hash")) that is always None for Zendesk's
        {"ticket": {...}} shape. The stored external_message_id then never
        matches the dedup query's message_id on redelivery, so a second
        identical event (same ticket id, different external_event_id --
        simulating a webhook redelivery or pull-cursor overlap) creates a
        second FeedbackItem instead of being deduped.
        """
        from src.tasks.source_events import process_source_event
        from src.models import FeedbackItem, FeedbackSourceEvent

        org = _make_org(db)
        _make_zendesk_integration(db, org.id, subdomain="acmeco")
        source = _make_zendesk_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        event_data = {
            "ticket": {
                "id": 555,
                "subject": "Cannot login",
                "description": "<p>Getting a 500 error</p>",
                "status": "open",
                "tags": ["auth"],
                "requester_email": "sam@customer.com",
            },
            "subdomain": "acmeco",
        }

        process_source_event(
            source_type="zendesk",
            external_event_id="evt-555-a",
            event_type="ticket.created",
            event_data=event_data,
            provider_context={"subdomain": "acmeco"},
        )
        second_result = process_source_event(
            source_type="zendesk",
            external_event_id="evt-555-b",
            event_type="ticket.created",
            event_data=event_data,
            provider_context={"subdomain": "acmeco"},
        )

        items = db.query(FeedbackItem).all()
        assert len(items) == 1

        processed_events = db.query(FeedbackSourceEvent).filter(
            FeedbackSourceEvent.source_id == source.id,
            FeedbackSourceEvent.status == "processed",
        ).all()
        assert len(processed_events) == 1
        assert processed_events[0].external_message_id == "555"

        assert second_result["status"] == "processed"
        assert second_result["results"][0]["status"] == "duplicate"

    def test_no_matching_source_is_a_logged_no_op_not_a_crash(
        self, db, monkeypatch, _no_op_side_effects
    ):
        from src.tasks.source_events import process_source_event
        from src.models import FeedbackItem

        org = _make_org(db)
        _make_zendesk_integration(db, org.id, subdomain="acmeco")
        _make_zendesk_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        result = process_source_event(
            source_type="zendesk",
            external_event_id="evt-999-a",
            event_type="ticket.created",
            event_data={
                "ticket": {"id": 999, "subject": "Hi"},
                "subdomain": "unknown-subdomain",
            },
            provider_context={"subdomain": "unknown-subdomain"},
        )

        assert result["status"] == "no_sources"
        assert db.query(FeedbackItem).count() == 0
