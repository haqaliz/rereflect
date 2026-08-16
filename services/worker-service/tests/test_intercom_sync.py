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


def _part(part_id, body, author=None, created_at=1785400000):
    """One reply part in the detail-GET shape (adapter-reply-rating-extraction
    fixture parity: `conversation_parts.conversation_parts[]`, part_type
    "comment", HTML body)."""
    return {
        "type": "conversation_part",
        "id": part_id,
        "part_type": "comment",
        "body": f"<p>{body}</p>",
        "author": author
        or {
            "type": "user",
            "id": "user_1",
            "name": "Dana Okafor",
            "email": "dana@example.com",
        },
        "created_at": created_at,
    }


def _conversation_detail(conv_id, replies, rating=None, email="dana@example.com"):
    """A conversation as GET /conversations/{id} returns it (R1b — the search
    object carries no parts; the detail payload does). Rating object is
    `conversation_rating`, matching Intercom's detail schema and the adapter's
    extract_rating reader."""
    return {
        "type": "conversation",
        "id": conv_id,
        "created_at": 1785390000,
        "updated_at": 1785400000,
        "conversation_message": {
            "type": "conversation",
            "id": f"msg_{conv_id}",
            "body": "<p>Billing is broken</p>",
            "author": {
                "type": "user",
                "id": f"contact_{conv_id}",
                "name": "Dana Okafor",
                "email": email,
            },
        },
        "conversation_parts": {"conversation_parts": replies},
        "conversation_rating": rating,
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

    Each page is (conversations, next_cursor, total_count), where the
    conversations are in the RAW search-API shape and `total_count` defaults
    to None (absent) -- concrete values ride in when the sync-estimate aspect
    needs them. The real client's `_normalize` is applied here so the fake
    returns exactly what the real one returns -- otherwise the sync tests
    would silently pass against a shape production never produces.
    """
    from src.clients.intercom import IntercomClient

    pages = [p + (None,) if len(p) == 2 else p for p in pages]
    client = MagicMock()
    client.search_conversations.side_effect = [
        (
            [IntercomClient._normalize(c) for c in convs],
            cursor,
            total_count,
        )
        for convs, cursor, total_count in pages
    ]
    client.close = MagicMock()
    return client


def _fake_client_with_parts(pages, detail_by_id=None):
    """`_fake_client` plus a `get_conversation` fed by a conversation-id →
    detail-payload map (R1b: parts ride on the detail GET, not the search
    object). Conversations absent from the map return {} — no parts, no
    rating, the same shape a 404/empty detail yields."""
    client = _fake_client(pages)
    detail_by_id = detail_by_id or {}

    def _get_conversation(conversation_id):
        return detail_by_id.get(conversation_id, {})

    client.get_conversation.side_effect = _get_conversation
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
        conversations, cursor, total_count = client.search_conversations(updated_since=0)

        assert cursor is None
        assert total_count is None
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

    def test_returns_total_count_when_present(self):
        """R1 — Intercom's per-query total_count rides the 3-tuple."""
        import httpx

        from src.clients.intercom import IntercomClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "conversations": [_conversation("c1", "Billing is broken")],
                    "pages": {"next": {"starting_after": "abc123"}},
                    "total_count": 42,
                },
            )

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        conversations, cursor, total_count = client.search_conversations(
            updated_since=0
        )

        assert total_count == 42
        assert cursor == "abc123"
        assert len(conversations) == 1

    def test_returns_none_when_total_count_absent(self):
        """Defensive — an envelope without total_count yields None, never a
        crash and never a fabricated number."""
        import httpx

        from src.clients.intercom import IntercomClient

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"conversations": [], "pages": {}}
            )

        client = IntercomClient("tok", transport=httpx.MockTransport(handler))
        _, _, total_count = client.search_conversations(updated_since=0)

        assert total_count is None


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


class TestSyncOrgEstimate:
    """sync-estimate: `_sync_org` computes backlog_remaining from the client's
    per-query total_count (max(0, total - seen), None when the total is
    unknown). The last page's total wins by construction — Intercom returns
    the same window total on every page of one query."""

    def test_computes_remaining_from_total_minus_seen(
        self, db, _no_op_side_effects
    ):
        """Two pages, same per-query total on both — pins the per-query
        semantics: 5 total, 3 seen across pages → 2 remaining."""
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client(
            [
                (
                    [_conversation("c1", "one"), _conversation("c2", "two")],
                    "cursor-1",
                    5,
                ),
                ([_conversation("c3", "three")], None, 5),
            ]
        )
        result = _sync_org(org.id, db, client, integ)

        assert result["conversations_seen"] == 3
        assert result["backlog_remaining"] == 2

    def test_drained_window_reports_zero(self, db, _no_op_side_effects):
        """total == seen → 0 (int, not None) — the drained-install signal."""
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client(
            [([_conversation("c1", "one"), _conversation("c2", "two"), _conversation("c3", "three")], None, 3)]
        )
        result = _sync_org(org.id, db, client, integ)

        assert result["backlog_remaining"] == 0
        assert isinstance(result["backlog_remaining"], int)

    def test_seen_can_exceed_total_without_a_negative_estimate(
        self, db, _no_op_side_effects
    ):
        """The `>=` boundary re-fetch inflates seen above the window total
        (a first-run inclusive window re-counts the boundary conversation).
        max(0, total - seen) must clamp to 0, never go negative."""
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client([([_conversation("c1", "one")], None, 0)])
        result = _sync_org(org.id, db, client, integ)

        assert result["backlog_remaining"] == 0

    def test_unknown_total_yields_none(self, db, _no_op_side_effects):
        """total_count absent from the payload → key present, value None —
        an honest 'no estimate this run', never a fabricated number."""
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client([([_conversation("c1", "one")], None, None)])
        result = _sync_org(org.id, db, client, integ)

        assert "backlog_remaining" in result
        assert result["backlog_remaining"] is None

    def test_empty_window_yields_none_when_total_unknown(
        self, db, _no_op_side_effects
    ):
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client([([], None, None)])
        result = _sync_org(org.id, db, client, integ)

        assert result["backlog_remaining"] is None

    def test_backlog_remaining_is_an_additive_key(
        self, db, _no_op_side_effects
    ):
        """The FULL result key set — the enrichment feature's
        changed_feedback_ids/dropped_by_cap are asserted present and
        untouched, so a future deletion of either cannot silently pass."""
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        client = _fake_client([([_conversation("c1", "one")], None, 5)])
        result = _sync_org(org.id, db, client, integ)

        assert set(result.keys()) == {
            "conversations_seen",
            "conversations_ingested",
            "changed_feedback_ids",
            "dropped_by_cap",
            "no_source_match",
            "cursor",
            "backlog_remaining",
        }


class TestSyncOrgEnrichment:
    """The pull-enrichment pass inside `_sync_org` (R1b path).

    Pinned via the shared core like the rest of TestSyncOrg: one item per
    conversation, created by the event loop; the enrichment pass then merges
    new reply parts + the rating into that SAME item. `changed_feedback_ids`
    is additive — it never inflates `conversations_ingested` (which counts
    items created this run).
    """

    def test_enriches_conversation_with_replies_and_rating(
        self, db, _no_op_side_effects
    ):
        """AC1 — one conversation, two replies + a rating → exactly ONE item
        whose text carries the merge blocks and whose metadata has replies +
        rating; the created item is the one reported as changed."""
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        detail = _conversation_detail(
            "c1",
            [_part("p1", "I fixed it"), _part("p2", "All good now")],
            rating={"type": "conversation_rating", "rating": 5, "remark": "Great support!"},
        )
        client = _fake_client_with_parts(
            [([_conversation("c1", "Billing is broken")], None)],
            {"c1": detail},
        )
        result = _sync_org(org.id, db, client, integ)
        db.commit()

        items = db.query(FeedbackItem).all()
        assert len(items) == 1
        item = items[0]
        assert item.text == (
            "Billing is broken"
            "\n\n--- Reply by Dana Okafor (1785400000) ---\nI fixed it"
            "\n\n--- Reply by Dana Okafor (1785400000) ---\nAll good now"
        )
        assert [r["part_id"] for r in item.source_metadata["replies"]] == ["p1", "p2"]
        assert item.source_metadata["rating"] == 5
        assert item.source_metadata["remark"] == "Great support!"
        assert result["conversations_ingested"] == 1
        assert result["changed_feedback_ids"] == [item.id]

    def test_redelivery_is_idempotent_for_parts(self, db, _no_op_side_effects):
        """AC2 — same conversation+parts across runs: the second run creates
        no item (dedup), changes no text, and reports no changed ids."""
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        conv = _conversation("c1", "Billing is broken")
        detail = _conversation_detail("c1", [_part("p1", "I fixed it")])
        client = _fake_client_with_parts([([conv], None), ([conv], None)], {"c1": detail})

        first = _sync_org(org.id, db, client, integ)
        db.commit()
        text_after_first = db.query(FeedbackItem).first().text
        metadata_after_first = dict(db.query(FeedbackItem).first().source_metadata)

        second = _sync_org(org.id, db, client, integ)
        db.commit()

        assert db.query(FeedbackItem).count() == 1
        assert second["conversations_ingested"] == 0
        item = db.query(FeedbackItem).first()
        assert item.text == text_after_first
        assert item.source_metadata == metadata_after_first
        assert first["changed_feedback_ids"] == [item.id]
        assert second["changed_feedback_ids"] == []

    def test_admin_reply_merged_but_never_attributed(self, db, _no_op_side_effects):
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        conv = _conversation("c1", "Billing is broken", email="dana@customer.com")
        admin = {"type": "admin", "id": "admin_1", "name": "Agent Ada"}
        detail = _conversation_detail("c1", [_part("p1", "Teammate reply", author=admin)])
        client = _fake_client_with_parts([([conv], None)], {"c1": detail})

        _sync_org(org.id, db, client, integ)
        db.commit()

        item = db.query(FeedbackItem).first()
        assert "Teammate reply" in item.text
        assert item.customer_email == "dana@customer.com"

    def test_enrichment_does_not_inflate_conversations_ingested(
        self, db, _no_op_side_effects
    ):
        """A pre-existing item that gains a reply on a later run dispatches
        re-analysis (changed_feedback_ids) without counting a new ingestion."""
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        conv = _conversation("c1", "Billing is broken")
        first = _sync_org(
            org.id, db, _fake_client_with_parts([([conv], None)], {}), integ
        )
        db.commit()
        assert first["conversations_ingested"] == 1
        item = db.query(FeedbackItem).first()
        assert "I fixed it" not in item.text

        detail = _conversation_detail("c1", [_part("p1", "I fixed it")])
        second = _sync_org(
            org.id, db, _fake_client_with_parts([([conv], None)], {"c1": detail}), integ
        )
        db.commit()

        assert second["conversations_ingested"] == 0
        assert second["changed_feedback_ids"] == [item.id]
        assert "I fixed it" in db.query(FeedbackItem).first().text

    def test_conversation_without_parts_is_a_noop(self, db, _no_op_side_effects):
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        conv = _conversation("c1", "Billing is broken")
        client = _fake_client_with_parts([([conv], None)], {"c1": {}})
        result = _sync_org(org.id, db, client, integ)
        db.commit()

        assert result["changed_feedback_ids"] == []
        assert client.get_conversation.call_count == 1
        item = db.query(FeedbackItem).first()
        assert item.text == "Billing is broken"

    def test_parts_without_an_item_are_a_noop(self, db, _no_op_side_effects):
        """A conversation the event loop did not turn into an item (empty
        text) is skipped by enrichment — the lookup finds nothing."""
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        conv = _conversation("c1", "a")  # < 3 chars → empty_text, no item
        detail = _conversation_detail("c1", [_part("p1", "I fixed it")])
        client = _fake_client_with_parts([([conv], None)], {"c1": detail})
        result = _sync_org(org.id, db, client, integ)

        assert db.query(FeedbackItem).count() == 0
        assert result["changed_feedback_ids"] == []

    def test_rating_only_change_updates_metadata_without_dispatch(
        self, db, _no_op_side_effects
    ):
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_source(db, org.id)

        conv = _conversation("c1", "Billing is broken")
        no_rating = _conversation_detail("c1", [_part("p1", "I fixed it")])
        with_rating = _conversation_detail(
            "c1",
            [_part("p1", "I fixed it")],
            rating={"type": "conversation_rating", "rating": 4},
        )
        client = _fake_client_with_parts(
            [([conv], None), ([conv], None)], {"c1": no_rating}
        )
        first = _sync_org(org.id, db, client, integ)
        db.commit()

        client = _fake_client_with_parts(
            [([conv], None), ([conv], None)], {"c1": with_rating}
        )
        second = _sync_org(org.id, db, client, integ)
        db.commit()

        item = db.query(FeedbackItem).first()
        assert first["changed_feedback_ids"] == [item.id]
        assert second["changed_feedback_ids"] == []
        assert item.source_metadata["rating"] == 4
        assert item.text.count("I fixed it") == 1

    def test_enrichment_is_org_scoped(self, db, _no_op_side_effects):
        """Same conversation id under two orgs sharing a workspace: the
        enrichment lookup is org-scoped, so a run for org A never touches
        org B's item."""
        from src.models import FeedbackItem
        from src.tasks.intercom_sync import _sync_org

        org_a = _make_org(db, "Org A")
        org_b = _make_org(db, "Org B")
        integ_a = _make_integration(db, org_a.id)
        integ_b = _make_integration(db, org_b.id)
        _make_source(db, org_a.id)
        _make_source(db, org_b.id)

        conv = _conversation("c1", "Billing is broken")
        detail = _conversation_detail("c1", [_part("p1", "I fixed it")])

        # A's run creates items under BOTH orgs (both sources match the
        # workspace) but enriches only org A's item.
        _sync_org(org_a.id, db, _fake_client_with_parts([([conv], None)], {"c1": detail}), integ_a)
        db.commit()

        items = db.query(FeedbackItem).order_by(FeedbackItem.organization_id).all()
        assert [i.organization_id for i in items] == sorted([org_a.id, org_b.id])
        item_a = next(i for i in items if i.organization_id == org_a.id)
        item_b = next(i for i in items if i.organization_id == org_b.id)
        assert "I fixed it" in item_a.text
        assert "I fixed it" not in item_b.text

        # B's run enriches only org B's item.
        _sync_org(org_b.id, db, _fake_client_with_parts([([conv], None)], {"c1": detail}), integ_b)
        db.commit()

        db.refresh(item_a)
        db.refresh(item_b)
        assert "I fixed it" in item_b.text
        assert item_a.text.count("I fixed it") == 1


class TestSyncOrgBodyPersistence:
    """sync-estimate: a completed run persists backlog_remaining on the
    integration row — the estimate (int), an honest None when the total was
    unknown (overwriting any stale number), and 0 when the window is drained."""

    def test_success_persists_estimate_on_the_row(
        self, db, monkeypatch, _no_op_side_effects
    ):
        from src.tasks.intercom_sync import _sync_intercom_org_body

        org = _make_org(db)
        integ = _make_integration(db, org.id, access_token=_encrypt("tok"))
        _make_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        import src.tasks.intercom_sync as mod

        monkeypatch.setenv("LLM_ENCRYPTION_KEY", ENCRYPTION_KEY)
        client = _fake_client([([], None, 5)])
        monkeypatch.setattr(mod, "IntercomClient", lambda *a, **k: client)

        result = _sync_intercom_org_body(MagicMock(), integ.id)

        assert result["status"] == "ok"
        assert result["backlog_remaining"] == 5
        db.refresh(integ)
        assert integ.last_sync_status == "ok"
        assert integ.backlog_remaining == 5

    def test_unknown_total_overwrites_a_stale_estimate(
        self, db, monkeypatch, _no_op_side_effects
    ):
        """A completed run with an unknown total writes None — never a stale
        number beside a fresh last_sync_status="ok" (PRD R3 risk decision)."""
        from src.tasks.intercom_sync import _sync_intercom_org_body

        org = _make_org(db)
        integ = _make_integration(db, org.id, access_token=_encrypt("tok"))
        integ.backlog_remaining = 3  # stale from a previous run
        db.commit()
        _make_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        import src.tasks.intercom_sync as mod

        monkeypatch.setenv("LLM_ENCRYPTION_KEY", ENCRYPTION_KEY)
        client = _fake_client([([], None, None)])
        monkeypatch.setattr(mod, "IntercomClient", lambda *a, **k: client)

        _sync_intercom_org_body(MagicMock(), integ.id)

        db.refresh(integ)
        assert integ.last_sync_status == "ok"
        assert integ.backlog_remaining is None

    def test_zero_estimate_persists_as_zero_not_null(
        self, db, monkeypatch, _no_op_side_effects
    ):
        """A drained window persists 0 — the sync writes the truth; the UI's
        'no row' rules are the frontend aspect's job."""
        from src.tasks.intercom_sync import _sync_intercom_org_body

        org = _make_org(db)
        integ = _make_integration(db, org.id, access_token=_encrypt("tok"))
        _make_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        import src.tasks.intercom_sync as mod

        monkeypatch.setenv("LLM_ENCRYPTION_KEY", ENCRYPTION_KEY)
        client = _fake_client([([_conversation("c1", "one")], None, 1)])
        monkeypatch.setattr(mod, "IntercomClient", lambda *a, **k: client)

        _sync_intercom_org_body(MagicMock(), integ.id)

        db.refresh(integ)
        assert integ.last_sync_status == "ok"
        assert integ.backlog_remaining == 0
        assert integ.backlog_remaining is not None


class TestSyncErrorResetsBacklog:
    """sync-estimate: a FAILED run never leaves a stale backlog_remaining
    beside a failed status — both error paths reset it to None (seeded with a
    stale value to prove the reset, not just absence)."""

    def test_auth_error_resets_backlog_remaining(
        self, db, monkeypatch, _no_op_side_effects
    ):
        """D7 — a static auth failure records auth_error without disconnecting;
        the stale estimate is cleared."""
        from src.clients.intercom import IntercomAuthError
        from src.tasks.intercom_sync import _sync_intercom_org_body

        org = _make_org(db)
        integ = _make_integration(db, org.id, access_token=_encrypt("tok"))
        integ.backlog_remaining = 7  # stale from a previous run
        db.commit()
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
        assert integ.backlog_remaining is None
        assert result["status"] == "error"

    def test_transient_error_resets_backlog_remaining(
        self, db, monkeypatch, _no_op_side_effects
    ):
        """A transient failure records transient_error and retries; the stale
        estimate is cleared."""
        from src.clients.intercom import IntercomTransientError
        from src.tasks.intercom_sync import _sync_intercom_org_body

        org = _make_org(db)
        integ = _make_integration(db, org.id, access_token=_encrypt("tok"))
        integ.backlog_remaining = 7  # stale from a previous run
        db.commit()
        _make_source(db, org.id)
        _patch_db_session(monkeypatch, db)

        import src.tasks.intercom_sync as mod

        monkeypatch.setenv("LLM_ENCRYPTION_KEY", ENCRYPTION_KEY)
        failing = MagicMock()
        failing.search_conversations.side_effect = IntercomTransientError("503")
        failing.close = MagicMock()
        monkeypatch.setattr(mod, "IntercomClient", lambda *a, **k: failing)

        task_self = MagicMock()
        task_self.retry.side_effect = IntercomTransientError("503")

        with pytest.raises(IntercomTransientError):
            _sync_intercom_org_body(task_self, integ.id)

        task_self.retry.assert_called_once()
        db.refresh(integ)
        assert integ.last_sync_status == "transient_error"
        assert integ.last_error
        assert integ.backlog_remaining is None


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
