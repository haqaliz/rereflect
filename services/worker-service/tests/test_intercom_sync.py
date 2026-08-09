"""Tests for the Intercom conversation-pull sync (pull-sync aspect).

This is the path the originating user ask actually named -- "so feedback flows
in automatically instead of pasting tickets manually". Before this, Intercom had
no pull path at all: IntercomConnector.fetch_new_items was a stub returning [].

Modelled on tests/test_zendesk_sync.py. The design decisions it inherits from
zendesk_sync.py are asserted here rather than assumed:

  * cursor = last_synced_at or connected_at -- never epoch/None, so a missing
    cursor can never trigger a historical backfill;
  * every conversation goes through the SHARED ingestion core
    (_find_matching_sources / _process_event_for_source), so pull and webhook
    share one dedup path rather than forking;
  * a static auth failure is operator-recoverable: record last_sync_status /
    last_error WITHOUT flipping is_active;
  * the token is never logged.

Where Intercom DIFFERS from Zendesk, and why the cursor logic is not a copy:
Zendesk's incremental endpoint returns an authoritative `end_time` watermark.
Intercom's conversation search has no such thing, so the cursor is derived from
the max `updated_at` observed. The query therefore uses `>=`, not `>`: `>` would
silently drop a conversation updated in the same second as the watermark but
returned after the page cap. `>=` guarantees no loss at the cost of re-fetching
the boundary conversation each run, which FeedbackSourceEvent dedup absorbs.

See docs/planning/intercom-selfhost-ingestion/pull-sync/.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.models import FeedbackSource, IntercomIntegration, Organization

WORKSPACE = "ws_pull_test"

# R4 — the worker's _decrypt must work in the worker import universe
# (src.utils.encryption does not exist in the worker image), so the production
# path is exercised with a REAL Fernet round-trip, never a monkeypatched _decrypt.
ENCRYPTION_KEY = "F5XVApZxzOVKc2xrZlnI6ouXipDzsxflzFn2Ki_5_yk="


def _encrypt(secret: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(ENCRYPTION_KEY.encode()).encrypt(secret.encode()).decode()


def _make_org(db, name="Pull Co") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_integration(db, org_id, connected_at=None, last_synced_at=None, access_token="enc:blob"):
    row = IntercomIntegration(
        organization_id=org_id,
        access_token=access_token,
        workspace_id=WORKSPACE,
        is_active=True,
        connected_at=connected_at or datetime(2026, 7, 1, 12, 0, 0),
        last_synced_at=last_synced_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_source(db, org_id):
    source = FeedbackSource(
        organization_id=org_id,
        integration_id=None,
        source_type="intercom",
        is_active=True,
        auto_import=True,
        triggers={"new_conversations": True},
        field_mapping={},
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _conversation(conv_id, body, email="dana@example.com", updated_at=1785400000):
    """A conversation as the search API returns it (2.x `source` shape)."""
    return {
        "type": "conversation",
        "id": conv_id,
        "created_at": updated_at - 10,
        "updated_at": updated_at,
        "source": {
            "type": "conversation",
            "id": f"msg_{conv_id}",
            "body": f"<p>{body}</p>",
            "author": {
                "type": "user",
                "id": f"contact_{conv_id}",
                "name": "Dana Okafor",
                "email": email,
            },
        },
    }


def _patch_db_session(monkeypatch, db):
    import src.tasks.intercom_sync as mod

    @contextmanager
    def fake_get_db():
        yield db

    monkeypatch.setattr(mod, "get_db_session", fake_get_db)


@pytest.fixture
def _no_op_side_effects(monkeypatch):
    import src.cache as cache_mod
    import src.tasks.analysis as analysis_mod

    monkeypatch.setattr(analysis_mod.analyze_single_feedback, "delay", MagicMock())
    monkeypatch.setattr(cache_mod, "cache_invalidate", MagicMock())


def _fake_client(pages):
    """A client whose search_conversations walks the given pages.

    Each page is (conversations, next_cursor), where the conversations are in
    the RAW search-API shape. The real client's `_normalize` is applied here so
    the fake returns exactly what the real one returns -- otherwise the sync
    tests would silently pass against a shape production never produces.
    """
    from src.clients.intercom import IntercomClient

    client = MagicMock()
    client.search_conversations.side_effect = [
        ([IntercomClient._normalize(c) for c in convs], cursor)
        for convs, cursor in pages
    ]
    client.close = MagicMock()
    return client


# ──────────────────────────── Client contract ─────────────────────────────────


class TestIntercomClientSearch:
    def test_builds_a_gte_updated_at_query(self):
        """The `>=` is deliberate -- see the module docstring. A `>` here would
        silently drop same-second conversations past the page cap."""
        import httpx

        from src.clients.intercom import IntercomClient

        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            captured["body"] = json.loads(request.content)
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"conversations": [], "pages": {}})

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        client.search_conversations(updated_since=1785400000)

        query = captured["body"]["query"]
        assert query["field"] == "updated_at"
        assert query["operator"] == ">="
        assert int(query["value"]) == 1785400000
        assert captured["auth"] == "Bearer tok"

    def test_normalizes_source_into_conversation_message(self):
        """The adapter's contract is the WEBHOOK envelope, which carries
        `conversation_message`. The search API returns the same content under
        `source`. Normalizing in the client keeps the adapter untouched and
        keeps pull and webhook on one extraction path."""
        import httpx

        from src.clients.intercom import IntercomClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "conversations": [_conversation("c1", "Billing is broken")],
                    "pages": {},
                },
            )

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        conversations, cursor = client.search_conversations(updated_since=0)

        assert cursor is None
        assert "conversation_message" in conversations[0]
        assert conversations[0]["conversation_message"]["author"]["email"] == (
            "dana@example.com"
        )

    def test_auth_failure_raises_auth_error(self):
        import httpx

        from src.clients.intercom import IntercomAuthError, IntercomClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"errors": [{"code": "unauthorized"}]})

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        with pytest.raises(IntercomAuthError):
            client.search_conversations(updated_since=0)

    def test_server_error_raises_transient_error(self):
        import httpx

        from src.clients.intercom import IntercomClient, IntercomTransientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        with pytest.raises(IntercomTransientError):
            client.search_conversations(updated_since=0)

    def test_rate_limit_raises_transient_error(self):
        """S2 -- 429 is transient, not an auth failure. Retrying is correct."""
        import httpx

        from src.clients.intercom import IntercomClient, IntercomTransientError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "30"})

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        with pytest.raises(IntercomTransientError):
            client.search_conversations(updated_since=0)


# ──────────────────────────── Sync core ───────────────────────────────────────


class TestSyncOrg:
    def test_ingests_a_conversation_as_feedback(self, db, _no_op_side_effects):
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client([([_conversation("c1", "Billing is broken")], None)])
        result = _sync_org(org.id, db, client, integ)
        db.commit()

        items = db.query(FeedbackItem).all()
        assert len(items) == 1
        assert items[0].text == "Billing is broken"
        assert result["conversations_ingested"] == 1

    def test_populates_customer_email(self, db, _no_op_side_effects):
        """R7 -- without this, ingested Intercom feedback is invisible to
        Customer 360, health scores and churn. That is the difference between
        'it arrives' and 'it is useful'."""
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client(
            [
                (
                    [
                        _conversation(
                            "c1",
                            "Exports keep timing out",
                            email="rea@customer.com",
                        )
                    ],
                    None,
                )
            ]
        )
        _sync_org(org.id, db, client, integ)
        db.commit()

        assert db.query(FeedbackItem).first().customer_email == "rea@customer.com"

    def test_cursor_starts_at_connected_at_never_epoch(self, db, _no_op_side_effects):
        """Inherited from zendesk_sync D1: a NULL cursor must never mean a
        historical backfill of the entire workspace."""
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        connected = datetime(2026, 7, 1, 12, 0, 0)
        integ = _make_integration(db, org.id, connected_at=connected, last_synced_at=None)
        _make_source(db, org.id)

        client = _fake_client([([], None)])
        _sync_org(org.id, db, client, integ)

        called_with = client.search_conversations.call_args.kwargs["updated_since"]
        assert called_with == int(connected.timestamp())
        assert called_with > 0

    def test_cursor_prefers_last_synced_at(self, db, _no_op_side_effects):
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        last_synced = datetime(2026, 7, 20, 8, 0, 0)
        integ = _make_integration(
            db, org.id, connected_at=datetime(2026, 7, 1), last_synced_at=last_synced
        )
        _make_source(db, org.id)

        client = _fake_client([([], None)])
        _sync_org(org.id, db, client, integ)

        assert client.search_conversations.call_args.kwargs["updated_since"] == int(
            last_synced.timestamp()
        )

    def test_cursor_advances_to_max_updated_at(self, db, _no_op_side_effects):
        """Intercom has no end_time watermark, so the cursor is derived."""
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client(
            [
                (
                    [
                        _conversation("c1", "one", updated_at=1785400000),
                        _conversation("c2", "two", updated_at=1785409999),
                    ],
                    None,
                )
            ]
        )
        _sync_org(org.id, db, client, integ)

        assert integ.last_synced_at == datetime.utcfromtimestamp(1785409999)

    def test_cursor_does_not_move_backwards_on_an_empty_page(
        self, db, _no_op_side_effects
    ):
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        last_synced = datetime(2026, 7, 20, 8, 0, 0)
        integ = _make_integration(db, org.id, last_synced_at=last_synced)
        _make_source(db, org.id)

        client = _fake_client([([], None)])
        _sync_org(org.id, db, client, integ)

        assert integ.last_synced_at == last_synced

    def test_follows_pagination(self, db, _no_op_side_effects):
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client(
            [
                ([_conversation("c1", "one")], "cursor-1"),
                ([_conversation("c2", "two")], None),
            ]
        )
        _sync_org(org.id, db, client, integ)
        db.commit()

        assert db.query(FeedbackItem).count() == 2
        assert client.search_conversations.call_count == 2
        assert (
            client.search_conversations.call_args_list[1].kwargs["starting_after"]
            == "cursor-1"
        )

    def test_redelivery_is_deduplicated(self, db, _no_op_side_effects):
        """The `>=` cursor re-fetches the boundary conversation by design; the
        shared FeedbackSourceEvent dedup is what makes that safe."""
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        conv = _conversation("c1", "Billing is broken")
        client = _fake_client([([conv], None), ([conv], None)])

        _sync_org(org.id, db, client, integ)
        db.commit()
        _sync_org(org.id, db, client, integ)
        db.commit()

        assert db.query(FeedbackItem).count() == 1

    def test_no_matching_source_is_a_logged_noop(self, db, _no_op_side_effects):
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        # deliberately no FeedbackSource

        client = _fake_client([([_conversation("c1", "hi")], None)])
        result = _sync_org(org.id, db, client, integ)

        assert result["no_source_match"] is True
        assert db.query(FeedbackItem).count() == 0


class TestAuthFailureHandling:
    def test_auth_error_records_status_without_deactivating(
        self, db, monkeypatch, _no_op_side_effects
    ):
        """Inherited from zendesk_sync D7: a static token failure is
        operator-recoverable. Disconnecting them on a typo'd token would be a
        surprising, unrequested destructive act."""
        from src.clients.intercom import IntercomAuthError
        from src.tasks.intercom_sync import _sync_intercom_org_body

        org = _make_org(db)
        integ = _make_integration(db, org.id, access_token=_encrypt("tok"))
        _make_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        import src.tasks.intercom_sync as mod

        monkeypatch.setenv("LLM_ENCRYPTION_KEY", ENCRYPTION_KEY)
        failing = MagicMock()
        failing.search_conversations.side_effect = IntercomAuthError("401")
        failing.close = MagicMock()
        monkeypatch.setattr(mod, "IntercomClient", lambda *a, **k: failing)

        result = _sync_intercom_org_body(MagicMock(), integ.id)

        db.refresh(integ)
        assert integ.is_active is True, "an auth failure must not disconnect the org"
        assert integ.last_sync_status == "auth_error"
        assert integ.last_error
        assert result["status"] == "error"

    def test_token_is_never_logged(self, db, monkeypatch, caplog, _no_op_side_effects):
        from src.tasks.intercom_sync import _sync_intercom_org_body

        org = _make_org(db)
        secret = "super-secret-token-value"
        integ = _make_integration(db, org.id, access_token=_encrypt(secret))
        _make_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        import src.tasks.intercom_sync as mod

        monkeypatch.setenv("LLM_ENCRYPTION_KEY", ENCRYPTION_KEY)
        client = _fake_client([([], None)])
        monkeypatch.setattr(mod, "IntercomClient", lambda *a, **k: client)

        with caplog.at_level("DEBUG"):
            _sync_intercom_org_body(MagicMock(), integ.id)

        assert secret not in caplog.text


class TestDecryptLocalFernet:
    """R4 — intercom_sync._decrypt must round-trip a real Fernet token WITHOUT
    any monkeypatch: src.utils.encryption does not exist in the worker image,
    so the old body raised ModuleNotFoundError on every call."""

    def test_decrypt_round_trips_a_real_fernet_token(self, monkeypatch):
        from src.tasks.intercom_sync import _decrypt

        monkeypatch.setenv("LLM_ENCRYPTION_KEY", ENCRYPTION_KEY)
        token = _encrypt("intercom-plain-secret")
        assert _decrypt(token) == "intercom-plain-secret"


class TestTaskRegistration:
    def test_tasks_are_registered_on_the_celery_app(self):
        """A task nobody scheduled is a feature nobody gets -- this repo has
        shipped that failure more than once."""
        from src.celery_app import celery_app

        assert "src.tasks.intercom_sync.sync_all_intercom" in celery_app.tasks
        assert "src.tasks.intercom_sync.sync_intercom_org" in celery_app.tasks

    def test_beat_schedule_includes_the_pull(self):
        from src.celery_app import celery_app

        entries = [
            entry["task"] for entry in celery_app.conf.beat_schedule.values()
        ]
        assert "src.tasks.intercom_sync.sync_all_intercom" in entries
