"""Contract tests for the Intercom webhook enrichment module (webhook-enrich-module
aspect).

Exercises `src.services.intercom_webhook_enrich.enrich_webhook_item` — the
worker service-layer module that turns a `conversation.user.replied` /
`conversation.rating.added` webhook event into a merge into the existing
per-conversation FeedbackItem, returning the status dict the core branch
(next aspect) dispatches on.

Strategy: in-memory SQLite (self-contained — does NOT rely on conftest's shared
engine), injectable IntercomClient, no Celery eager mode. Token decryption is a
REAL Fernet round-trip (house rule — `_decrypt` is never monkeypatched), so
tokens are stored encrypted with TEST_FERNET_KEY and the tests set
LLM_ENCRYPTION_KEY to that key per-call. Mirrors the test_intercom_writeback_task.py
harness.

Payloads are INLINE (the golden fixtures are a sibling aspect and may not be on
this branch yet) but match the pinned conversation-wrapped shape exactly:
`data.item.id` == conversation id; reply parts at
`item.conversation_parts.conversation_parts[]`; rating at `item.conversation_rating`.

THE INJECTION SEAM (plan §2.3 / ambiguity A5):
Because `IntercomClient` is LAZY-imported inside `_fetch_conversation`, tests
patch the REAL attribute `src.clients.intercom.IntercomClient` (a
`from X import Y` resolves Y at call time). `patch.object(intercom_webhook_enrich,
"IntercomClient", ...)` would NOT work — the lazy import rebinds the real class.
Do not "fix" this into a module-level import; that would break the seam.

Contract pinned here is the plan §1.2 table: enriched / noop/no_item /
noop/not_found / error/auth_error / error/no_connection, `changed` True only when
`item.text` changed, `feedback_id` set only on enriched. `IntercomTransientError`
is the ONLY exception that escapes (task retry path).

See docs/planning/intercom-webhook-reply-rating/webhook-enrich-module/.
"""
from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.clients.intercom import IntercomTransientError
from src.models import (
    Base,
    FeedbackItem,
    FeedbackSource,
    Integration,
    IntercomIntegration,
    Organization,
)

# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated — self-contained per spec)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)

# Real Fernet key for the house-rule round-trip decrypt tests (the same key the
# writeback/enrichment suites use for LLM_ENCRYPTION_KEY).
TEST_FERNET_KEY = "F5XVApZxzOVKc2xrZlnI6ouXipDzsxflzFn2Ki_5_yk="


def _encrypt(secret: str) -> str:
    from cryptography.fernet import Fernet

    return Fernet(TEST_FERNET_KEY.encode()).encrypt(secret.encode()).decode()


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture
def db() -> Session:
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session, name="Webhook Co") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_connection(db: Session, org_id: int, **overrides) -> IntercomIntegration:
    """Token-paste IntercomIntegration row (the primary Intercom install)."""
    now = datetime.utcnow()
    defaults = dict(
        organization_id=org_id,
        access_token=_encrypt("plain-token"),
        workspace_id="ws-1",
        workspace_name="Test Workspace",
        is_active=True,
        connected_at=now,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    row = IntercomIntegration(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_source(db: Session, org_id: int, **overrides) -> FeedbackSource:
    defaults = dict(
        organization_id=org_id,
        integration_id=None,
        source_type="intercom",
        name="Intercom",
        is_active=True,
        auto_import=True,
        triggers={"new_conversations": True},
        field_mapping={},
    )
    defaults.update(overrides)
    row = FeedbackSource(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_item(
    db: Session, org_id: int, conv_id="conv_1", text="First message", **overrides
) -> FeedbackItem:
    defaults = dict(
        organization_id=org_id,
        text=text,
        source="intercom",
        source_external_id=conv_id,
        customer_email="dana@acme.com",
        created_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    row = FeedbackItem(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Inline conversation-wrapped payload helpers
# ---------------------------------------------------------------------------

USER_AUTHOR = {
    "type": "user",
    "id": "user_1",
    "name": "Dana Okafor",
    "email": "dana@acme.com",
}
ADMIN_AUTHOR = {
    "type": "admin",
    "id": "admin_7",
    "name": "Priya Sharma",
    "email": "priya@acme.com",
}


def _part(part_id, body, author=None, created_at="2026-08-01T10:00:00Z"):
    """One reply part in the detail/webhook shape: `conversation_parts[]` entry,
    part_type "comment", HTML body."""
    return {
        "type": "conversation_part",
        "id": part_id,
        "part_type": "comment",
        "body": f"<p>{body}</p>",
        "author": author or USER_AUTHOR,
        "created_at": created_at,
    }


def _conversation_item(conv_id, parts=None, rating=None):
    """The `data.item` object in the conversation-wrapped webhook shape:
    item.id == conversation id; parts under conversation_parts.conversation_parts[];
    rating under conversation_rating."""
    item = {"type": "conversation", "id": conv_id}
    if parts is not None:
        item["conversation_parts"] = {"conversation_parts": parts}
    if rating is not None:
        item["conversation_rating"] = rating
    return item


def _reply_payload(conv_id, parts=None, rating=None):
    """A `conversation.user.replied` envelope (pinned conversation-wrapped shape)."""
    return {
        "type": "notification_event",
        "topic": "conversation.user.replied",
        "id": "notif_1",
        "app_id": "ws-1",
        "created_at": 1785400000,
        "data": {"type": "notification_event_data", "item": _conversation_item(conv_id, parts, rating)},
    }


def _rating_payload(conv_id, rating):
    """A `conversation.rating.added` envelope (pinned conversation-wrapped shape)."""
    return {
        "type": "notification_event",
        "topic": "conversation.rating.added",
        "id": "notif_2",
        "app_id": "ws-1",
        "created_at": 1785400000,
        "data": {"type": "notification_event_data", "item": _conversation_item(conv_id, rating=rating)},
    }


def _detail(conv_id, parts=None, rating=None):
    """A `get_conversation` fallback payload (detail shape, same parts/rating keys)."""
    return _conversation_item(conv_id, parts, rating)


# ---------------------------------------------------------------------------
# Fake client + runner
# ---------------------------------------------------------------------------


def _fake_client(detail_by_id=None):
    """Injectable IntercomClient shaped like writeback's `_make_mock_client`:
    a MagicMock with `__enter__`/`__exit__` returning self/False, and a
    `get_conversation` fed by a conversation-id → payload map (the
    `_fake_client_with_parts` idiom, test_intercom_sync.py:201). Conversations
    absent from the map return {} — no parts, no rating, the same shape a
    404/empty detail yields (fallback-200-with-nothing)."""
    mc = MagicMock()
    mc.__enter__ = MagicMock(return_value=mc)
    mc.__exit__ = MagicMock(return_value=False)
    detail_by_id = detail_by_id or {}

    def _get_conversation(conversation_id):
        return detail_by_id.get(conversation_id, {})

    mc.get_conversation.side_effect = _get_conversation
    return mc


def _run(
    db,
    source,
    event_data,
    client=None,
    event_type="conversation.user.replied",
    key=TEST_FERNET_KEY,
):
    """Run enrich_webhook_item with `src.clients.intercom.IntercomClient` patched
    to a MagicMock constructor returning `client` (the injectable fake).

    A5 (plan §2.3): the seam is patching the REAL attribute
    `src.clients.intercom.IntercomClient` — the module lazy-imports it inside
    `_fetch_conversation`, so `from X import Y` resolves Y at call time.
    `patch.object(intercom_webhook_enrich, "IntercomClient", ...)` would NOT
    work. Do not "fix" this into a module-level import.

    Returns (result, fake_cls) so tests can assert the constructor was/wasn't
    invoked and that get_conversation was/wasn't called.
    """
    from src.services import intercom_webhook_enrich as mod

    if client is None:
        client = _fake_client({})
    env = {}
    if key is not None:
        env["LLM_ENCRYPTION_KEY"] = key
    fake_cls = MagicMock(return_value=client)
    with patch.dict(os.environ, env, clear=True):
        with patch("src.clients.intercom.IntercomClient", fake_cls):
            result = mod.enrich_webhook_item(db, source, event_type, event_data)
    return result, fake_cls


# ---------------------------------------------------------------------------
# Item lookup
# ---------------------------------------------------------------------------


class TestItemLookup:
    def test_conversation_id_drives_item_lookup(self, db):
        """Envelope data.item.id == "conv_1" matches the item's
        source_external_id; result enriched; feedback_id == item.id."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, conv_id="conv_1")
        payload = _reply_payload("conv_1", parts=[_part("p1", "Happy to help")])

        result, fake_cls = _run(db, source, payload)

        assert result == {"status": "enriched", "changed": True, "feedback_id": item.id}
        fake_cls.assert_not_called()

    def test_no_item_returns_noop_no_item(self, db):
        """No FeedbackItem for the conversation → noop/no_item; get_conversation
        NOT called; count stays 0."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        client = _fake_client({})

        result, fake_cls = _run(db, source, _reply_payload("conv_1"), client=client)

        assert result == {"status": "noop/no_item", "changed": False, "feedback_id": None}
        fake_cls.assert_not_called()
        client.get_conversation.assert_not_called()
        assert db.query(FeedbackItem).count() == 0

    def test_missing_conversation_id_returns_noop_no_item(self, db):
        """Envelope without data.item.id (or missing data) → noop/no_item, no
        client call, no raise."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        client = _fake_client({})

        malformed = (
            {"data": {"item": {}}},
            {"data": {}},
            {},
            {"data": {"item": None}},
            {"data": None},
        )
        for payload in malformed:
            result, fake_cls = _run(db, source, payload, client=client)
            assert result == {"status": "noop/no_item", "changed": False, "feedback_id": None}
            fake_cls.assert_not_called()
            client.get_conversation.assert_not_called()


# ---------------------------------------------------------------------------
# Payload-first merge
# ---------------------------------------------------------------------------


class TestPayloadFirstMerge:
    def test_payload_first_parts_and_rating_skip_fetch(self, db):
        """Payload carries conversation_parts.conversation_parts[] and
        conversation_rating; get_conversation never called; text gains the
        pinned merge block; source_metadata replies/rating set; enriched,
        changed True, feedback_id set."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        payload = _reply_payload(
            "conv_1",
            parts=[_part("p1", "I fixed it")],
            rating={"rating": 5, "remark": "Great support!"},
        )
        client = _fake_client({})

        result, fake_cls = _run(db, source, payload, client=client)

        assert result == {"status": "enriched", "changed": True, "feedback_id": item.id}
        fake_cls.assert_not_called()
        client.get_conversation.assert_not_called()
        assert item.text == (
            "First message"
            "\n\n--- Reply by Dana Okafor (2026-08-01T10:00:00Z) ---\nI fixed it"
        )
        assert item.source_metadata["replies"][0]["part_id"] == "p1"
        assert item.source_metadata["rating"] == 5
        assert item.source_metadata["remark"] == "Great support!"

    def test_payload_rating_only_skip_fetch_changed_false(self, db):
        """Rating-only payload; no fetch; changed False; rating/remark in
        metadata; text unchanged."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        payload = _rating_payload("conv_1", {"rating": 4, "remark": "Decent"})
        client = _fake_client({})

        result, fake_cls = _run(db, source, payload, client=client, event_type="conversation.rating.added")

        assert result == {"status": "enriched", "changed": False, "feedback_id": item.id}
        fake_cls.assert_not_called()
        client.get_conversation.assert_not_called()
        assert item.text == "First message"
        assert item.source_metadata["rating"] == 4
        assert item.source_metadata["remark"] == "Decent"


# ---------------------------------------------------------------------------
# Fallback fetch
# ---------------------------------------------------------------------------


class TestFallbackFetch:
    def test_fallback_fetch_when_payload_has_no_parts(self, db):
        """Payload with neither parts nor rating; get_conversation("conv_1")
        called once; merge from fetched detail; enriched, changed True."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        detail = _detail(
            "conv_1",
            parts=[_part("p2", "Reply via detail", created_at="2026-08-01T11:00:00Z")],
            rating={"rating": 3},
        )
        client = _fake_client({"conv_1": detail})

        result, fake_cls = _run(db, source, _reply_payload("conv_1"), client=client)

        assert result == {"status": "enriched", "changed": True, "feedback_id": item.id}
        fake_cls.assert_called_once()
        client.get_conversation.assert_called_once_with("conv_1")
        assert "Reply via detail" in item.text
        assert item.source_metadata["replies"][0]["part_id"] == "p2"
        assert item.source_metadata["rating"] == 3

    def test_fallback_404_returns_noop_not_found(self, db):
        """get_conversation → IntercomNotFoundError → noop/not_found; changed
        False, feedback_id None; item untouched."""
        from src.clients.intercom import IntercomNotFoundError

        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        client = _fake_client({})
        client.get_conversation.side_effect = IntercomNotFoundError("gone")

        result, fake_cls = _run(db, source, _reply_payload("conv_1"), client=client)

        assert result == {"status": "noop/not_found", "changed": False, "feedback_id": None}
        fake_cls.assert_called_once()
        assert item.text == "First message"
        assert item.source_metadata is None

    def test_fallback_auth_error_returns_error_auth_error(self, db):
        """get_conversation → IntercomAuthError → error/auth_error; item
        untouched; no raise."""
        from src.clients.intercom import IntercomAuthError

        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        client = _fake_client({})
        client.get_conversation.side_effect = IntercomAuthError("rejected")

        result, fake_cls = _run(db, source, _reply_payload("conv_1"), client=client)

        assert result == {"status": "error/auth_error", "changed": False, "feedback_id": None}
        fake_cls.assert_called_once()
        assert item.text == "First message"

    def test_fallback_transient_raises_for_retry(self, db):
        """get_conversation → IntercomTransientError (429/5xx/network) →
        pytest.raises(IntercomTransientError); no status dict returned (task
        retry path)."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        _make_item(db, org.id, text="First message")
        client = _fake_client({})
        client.get_conversation.side_effect = IntercomTransientError("rate limited")

        with pytest.raises(IntercomTransientError):
            _run(db, source, _reply_payload("conv_1"), client=client)

    def test_no_connection_returns_error_no_connection(self, db):
        """No IntercomIntegration and no OAuth Integration row →
        error/no_connection (no client construct)."""
        org = _make_org(db)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        client = _fake_client({})

        result, fake_cls = _run(db, source, _reply_payload("conv_1"), client=client)

        assert result == {"status": "error/no_connection", "changed": False, "feedback_id": None}
        fake_cls.assert_not_called()
        client.get_conversation.assert_not_called()
        assert item.text == "First message"

    def test_missing_key_returns_error_auth_error(self, db):
        """LLM_ENCRYPTION_KEY unset → error/auth_error, no client construct, no
        raise (R6 non-retry semantics — config, not transient)."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        client = _fake_client({})

        result, fake_cls = _run(db, source, _reply_payload("conv_1"), client=client, key=None)

        assert result == {"status": "error/auth_error", "changed": False, "feedback_id": None}
        fake_cls.assert_not_called()
        client.get_conversation.assert_not_called()
        assert item.text == "First message"


# ---------------------------------------------------------------------------
# Merge idempotency + changed-flag semantics
# ---------------------------------------------------------------------------


class TestMergeIdempotency:
    def test_redelivery_is_idempotent(self, db):
        """Same payload delivered twice: 1st changed True; 2nd enriched,
        changed False; text and metadata byte-identical; count stays 1."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        payload = _reply_payload("conv_1", parts=[_part("p1", "I fixed it")])
        client = _fake_client({})

        result1, _ = _run(db, source, payload, client=client)
        text_after_first = item.text
        metadata_after_first = dict(item.source_metadata)

        result2, _ = _run(db, source, payload, client=client)

        assert result1 == {"status": "enriched", "changed": True, "feedback_id": item.id}
        assert result2 == {"status": "enriched", "changed": False, "feedback_id": item.id}
        assert item.text == text_after_first
        assert item.source_metadata == metadata_after_first
        assert db.query(FeedbackItem).count() == 1

    def test_changed_true_only_when_text_changed(self, db):
        """New reply → True; rating-only re-delivery on an already-merged item →
        False."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")

        reply_payload = _reply_payload("conv_1", parts=[_part("p1", "Brand new reply")])
        result1, _ = _run(db, source, reply_payload)

        assert result1 == {"status": "enriched", "changed": True, "feedback_id": item.id}

        rating_payload = _rating_payload("conv_1", {"rating": 2, "remark": "Meh"})
        result2, _ = _run(db, source, rating_payload, event_type="conversation.rating.added")

        assert result2 == {"status": "enriched", "changed": False, "feedback_id": item.id}


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


class TestInvariants:
    def test_rating_metadata_only_never_in_text(self, db):
        """Rating value/remark never appear in item.text."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message")
        payload = _rating_payload("conv_1", {"rating": 5, "remark": "Great support!"})

        result, _ = _run(db, source, payload, event_type="conversation.rating.added")

        assert result["status"] == "enriched"
        assert item.text == "First message"
        assert "Great support!" not in item.text
        assert "5" not in item.text

    def test_never_creates_items(self, db):
        """Across payload-first, fallback, no-item, 404, auth branches:
        FeedbackItem count never exceeds the pre-existing 1 (assert after each
        branch)."""
        from src.clients.intercom import IntercomAuthError, IntercomNotFoundError

        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        _make_item(db, org.id, text="First message")

        payload_first = _reply_payload("conv_1", parts=[_part("p1", "via payload")])
        result, _ = _run(db, source, payload_first)
        assert result["status"] == "enriched"
        assert db.query(FeedbackItem).count() == 1

        detail = _detail("conv_1", parts=[_part("p2", "via fallback")])
        fallback_client = _fake_client({"conv_1": detail})
        result, _ = _run(db, source, _reply_payload("conv_1"), client=fallback_client)
        assert result["status"] == "enriched"
        assert db.query(FeedbackItem).count() == 1

        no_item_client = _fake_client({})
        result, _ = _run(db, source, _reply_payload("conv_none"), client=no_item_client)
        assert result["status"] == "noop/no_item"
        assert db.query(FeedbackItem).count() == 1

        not_found_client = _fake_client({})
        not_found_client.get_conversation.side_effect = IntercomNotFoundError("gone")
        result, _ = _run(db, source, _reply_payload("conv_1"), client=not_found_client)
        assert result["status"] == "noop/not_found"
        assert db.query(FeedbackItem).count() == 1

        auth_client = _fake_client({})
        auth_client.get_conversation.side_effect = IntercomAuthError("rejected")
        result, _ = _run(db, source, _reply_payload("conv_1"), client=auth_client)
        assert result["status"] == "error/auth_error"
        assert db.query(FeedbackItem).count() == 1

    def test_customer_email_never_touched(self, db):
        """Item created with customer_email="dana@acme.com"; admin-author reply
        payload merged → customer_email unchanged; the admin is never attributed
        as the customer (reply body still carried in text)."""
        org = _make_org(db)
        _make_connection(db, org.id)
        source = _make_source(db, org.id)
        item = _make_item(db, org.id, text="First message", customer_email="dana@acme.com")
        payload = _reply_payload("conv_1", parts=[_part("p1", "Teammate reply", author=ADMIN_AUTHOR)])

        result, _ = _run(db, source, payload)

        assert result["status"] == "enriched"
        assert result["changed"] is True
        assert item.customer_email == "dana@acme.com"
        assert "Teammate reply" in item.text
        assert item.source_metadata["replies"][0]["author"]["type"] == "admin"
        assert "priya@acme.com" not in (item.customer_email or "")
