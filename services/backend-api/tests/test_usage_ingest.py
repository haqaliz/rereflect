"""
Tests for ingestion-receiver — POST /api/v1/webhooks/usage.

TDD: RED → GREEN per phase.

Coverage (spec acceptance criteria 1-7):
  1. Valid mixed batch → 202, correct accepted/skipped counts, 1 DB row written.
  2. No key → 401; valid key without ingest scope → 403.
  3. >1000 events → 413, nothing written.
  4. Duplicate messageId (same org) → not double-written; counted duplicate, still 202.
  5. Tenancy: rows carry auth.organization_id (cross-tenant isolation).
  6. properties >16 KB → truncated/dropped, event still ingests.
  7. Accepted events enqueued to src.tasks.usage_metrics.process_usage_event (mocked).

Phase 1 also covers schema-level unit tests:
  - Valid event accepted.
  - Unknown type rejected (422).
  - Email resolved from traits.
  - No-email flagging logic (helper).
"""

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.session import get_db
from src.models.api_key import ApiKey
from src.models.base import Base
from src.models.organization import Organization

# ── In-memory SQLite engine (isolated from conftest) ─────────────────────────

_SQLITE_URL = "sqlite:///:memory:"
_engine = create_engine(
    _SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=_engine)
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_api_key(db: Session, org_id: int, scopes: str = "ingest") -> tuple[str, ApiKey]:
    """Create a stored ApiKey and return (full_key, orm_row)."""
    raw = f"rrf_{secrets.token_urlsafe(24)}"
    prefix = raw[:10]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = ApiKey(
        organization_id=org_id,
        name="test ingest key",
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes,
        revoked_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def _make_org(db: Session, name: str = "Acme") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _track_event(msg_id: str = "msg-001", email: str = "alice@example.com") -> dict:
    return {
        "type": "track",
        "email": email,
        "event": "login",
        "name": "Login",
        "messageId": msg_id,
        "timestamp": "2026-06-28T10:00:00Z",
        "properties": {"plan": "pro"},
    }


def _identify_event(msg_id: str = "msg-002") -> dict:
    return {
        "type": "identify",
        "traits": {"email": "bob@example.com", "name": "Bob"},
        "messageId": msg_id,
        "timestamp": "2026-06-28T11:00:00Z",
    }


# ─────────────────────────────────────────────────────────────────────────────
# § Phase 1 — Schema unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestUsageSchemas:
    """Unit tests for the Pydantic schemas (no HTTP, no DB)."""

    def test_valid_track_event_accepted(self):
        """A well-formed track event parses without error."""
        from src.api.schemas.usage import UsageEventIn
        ev = UsageEventIn(
            type="track",
            email="alice@example.com",
            event="login",
            name="Login",
            messageId="msg-abc",
            timestamp=datetime.now(timezone.utc),
            properties={"plan": "pro"},
        )
        assert ev.type == "track"
        assert ev.email == "alice@example.com"

    def test_valid_identify_event_accepted(self):
        """A well-formed identify event parses without error."""
        from src.api.schemas.usage import UsageEventIn
        ev = UsageEventIn(
            type="identify",
            traits={"email": "bob@example.com"},
            messageId="msg-xyz",
        )
        assert ev.type == "identify"

    def test_unknown_type_rejected(self):
        """An unknown event type is rejected with a validation error."""
        from pydantic import ValidationError
        from src.api.schemas.usage import UsageEventIn
        with pytest.raises(ValidationError):
            UsageEventIn(type="page", messageId="msg-1")

    def test_email_resolved_from_direct_field(self):
        """resolve_email returns the email field when present."""
        from src.api.schemas.usage import UsageEventIn, resolve_email
        ev = UsageEventIn(type="track", email="alice@example.com", messageId="m1")
        assert resolve_email(ev) == "alice@example.com"

    def test_email_resolved_from_traits(self):
        """resolve_email falls back to traits.email when email field is absent."""
        from src.api.schemas.usage import UsageEventIn, resolve_email
        ev = UsageEventIn(
            type="identify",
            traits={"email": "trait@example.com"},
            messageId="m2",
        )
        assert resolve_email(ev) == "trait@example.com"

    def test_email_unresolvable_returns_none(self):
        """resolve_email returns None when neither email nor traits.email is set."""
        from src.api.schemas.usage import UsageEventIn, resolve_email
        ev = UsageEventIn(type="track", userId="user-123", messageId="m3")
        assert resolve_email(ev) is None

    def test_properties_size_guard_large_passes_with_flag(self):
        """Properties >16 KB are truncated and flagged; no exception raised."""
        from src.api.schemas.usage import guard_properties
        big = {"key": "x" * (17 * 1024)}  # >16 KB
        result, truncated = guard_properties(big)
        assert truncated is True
        assert result == {}  # truncated to empty dict

    def test_properties_size_guard_small_passes_clean(self):
        """Properties <=16 KB pass through unchanged."""
        from src.api.schemas.usage import guard_properties
        small = {"plan": "pro", "feature": "dashboard"}
        result, truncated = guard_properties(small)
        assert truncated is False
        assert result == small

    def test_batch_accepts_up_to_1000_events(self):
        """UsageBatchIn allows exactly 1000 events without error."""
        from src.api.schemas.usage import UsageBatchIn, UsageEventIn
        events = [
            UsageEventIn(type="track", email=f"u{i}@x.com", messageId=f"m{i}")
            for i in range(1000)
        ]
        batch = UsageBatchIn(events=events)
        assert len(batch.events) == 1000


# ─────────────────────────────────────────────────────────────────────────────
# § Phase 3 — Integration tests (acceptance criteria 1-7)
# ─────────────────────────────────────────────────────────────────────────────

USAGE_URL = "/api/v1/webhooks/usage"

_CELERY_PATCH = "src.background.celery_client.get_celery_app"


def _celery_mock():
    """Return a context manager that patches get_celery_app and captures send_task calls."""
    mock_app = MagicMock()
    mock_app.send_task.return_value.id = "fake-task-id"
    return patch(_CELERY_PATCH, return_value=mock_app), mock_app


class TestUsageIngestAuth:
    """AC2 — authentication and scope enforcement."""

    def test_no_key_returns_401(self, client: TestClient):
        resp = client.post(USAGE_URL, json={"events": [_track_event()]})
        assert resp.status_code == 401

    def test_invalid_key_returns_401(self, client: TestClient):
        resp = client.post(
            USAGE_URL,
            json={"events": [_track_event()]},
            headers={"X-API-Key": "rrf_invalidkey"},
        )
        assert resp.status_code == 401

    def test_read_scope_only_returns_403(self, client: TestClient, db: Session):
        org = _make_org(db)
        raw_key, _ = _make_api_key(db, org.id, scopes="read")
        patcher, _ = _celery_mock()
        with patcher:
            resp = client.post(
                USAGE_URL,
                json={"events": [_track_event()]},
                headers={"X-API-Key": raw_key},
            )
        assert resp.status_code == 403


class TestUsageIngestBounds:
    """AC3 — >1000 events → 413, nothing written."""

    def test_over_1000_events_returns_413(self, client: TestClient, db: Session):
        from src.models.usage_event import UsageEvent

        org = _make_org(db)
        raw_key, _ = _make_api_key(db, org.id)
        events = [
            {"type": "track", "email": f"u{i}@x.com", "messageId": f"m{i}", "event": "login"}
            for i in range(1001)
        ]
        patcher, _ = _celery_mock()
        with patcher:
            resp = client.post(
                USAGE_URL,
                json={"events": events},
                headers={"X-API-Key": raw_key},
            )
        assert resp.status_code == 413
        # Nothing written
        count = db.query(UsageEvent).count()
        assert count == 0


class TestUsageIngestValidBatch:
    """AC1 — valid mixed batch → 202 with correct counts + 1 row."""

    def test_mixed_batch_accepted_and_skipped(self, client: TestClient, db: Session):
        from src.models.usage_event import UsageEvent

        org = _make_org(db)
        raw_key, _ = _make_api_key(db, org.id)
        events = [
            _track_event("msg-001", "alice@example.com"),  # accepted
            {
                "type": "track",
                "userId": "anon-user",  # no email
                "event": "click",
                "messageId": "msg-002",
            },  # skipped: no_email
        ]
        patcher, mock_app = _celery_mock()
        with patcher:
            resp = client.post(
                USAGE_URL,
                json={"events": events},
                headers={"X-API-Key": raw_key},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["accepted"] == 1
        assert body["skipped"] == 1
        assert body["skipped_reasons"]["no_email"] == 1

        # 1 row written
        rows = db.query(UsageEvent).filter(UsageEvent.organization_id == org.id).all()
        assert len(rows) == 1
        assert rows[0].customer_email == "alice@example.com"
        assert rows[0].external_event_id == "msg-001"

    def test_missing_message_id_skipped(self, client: TestClient, db: Session):
        from src.models.usage_event import UsageEvent

        org = _make_org(db)
        raw_key, _ = _make_api_key(db, org.id)
        events = [
            {
                "type": "track",
                "email": "alice@example.com",
                "event": "login",
                # no messageId
            }
        ]
        patcher, _ = _celery_mock()
        with patcher:
            resp = client.post(
                USAGE_URL,
                json={"events": events},
                headers={"X-API-Key": raw_key},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["accepted"] == 0
        assert body["skipped"] == 1
        assert body["skipped_reasons"].get("no_message_id", 0) == 1
        assert db.query(UsageEvent).count() == 0


class TestUsageIngestDedup:
    """AC4 — duplicate messageId not double-written."""

    def test_duplicate_message_id_not_written_twice(self, client: TestClient, db: Session):
        from src.models.usage_event import UsageEvent

        org = _make_org(db)
        raw_key, _ = _make_api_key(db, org.id)
        event = _track_event("dedup-msg-001")

        patcher, mock_app = _celery_mock()
        with patcher:
            # First POST
            r1 = client.post(
                USAGE_URL,
                json={"events": [event]},
                headers={"X-API-Key": raw_key},
            )
        assert r1.status_code == 202
        assert r1.json()["accepted"] == 1

        patcher2, mock_app2 = _celery_mock()
        with patcher2:
            # Second POST with same messageId
            r2 = client.post(
                USAGE_URL,
                json={"events": [event]},
                headers={"X-API-Key": raw_key},
            )
        assert r2.status_code == 202
        body2 = r2.json()
        assert body2["accepted"] == 0
        assert body2["skipped"] == 1
        assert body2["skipped_reasons"].get("duplicate", 0) == 1

        # Only 1 row in DB
        rows = db.query(UsageEvent).filter(UsageEvent.organization_id == org.id).all()
        assert len(rows) == 1


class TestUsageIngestTenancy:
    """AC5 — rows carry auth.organization_id (tenancy isolation)."""

    def test_rows_scoped_to_key_org_not_body(self, client: TestClient, db: Session):
        from src.models.usage_event import UsageEvent

        org_a = _make_org(db, "OrgA")
        org_b = _make_org(db, "OrgB")
        raw_key_a, _ = _make_api_key(db, org_a.id)

        # Key belongs to org_a — even if a malicious body omits/spoofs org
        events = [_track_event("msg-ten-001")]

        patcher, _ = _celery_mock()
        with patcher:
            resp = client.post(
                USAGE_URL,
                json={"events": events},
                headers={"X-API-Key": raw_key_a},
            )
        assert resp.status_code == 202

        rows = db.query(UsageEvent).all()
        assert len(rows) == 1
        assert rows[0].organization_id == org_a.id
        # org_b has zero rows
        org_b_rows = db.query(UsageEvent).filter(UsageEvent.organization_id == org_b.id).all()
        assert len(org_b_rows) == 0


class TestUsageIngestLargeProperties:
    """AC6 — properties >16 KB truncated, event still ingests."""

    def test_large_properties_truncated_and_ingested(self, client: TestClient, db: Session):
        from src.models.usage_event import UsageEvent

        org = _make_org(db)
        raw_key, _ = _make_api_key(db, org.id)
        big_props = {"data": "x" * (17 * 1024)}  # ~17 KB
        events = [
            {
                "type": "track",
                "email": "alice@example.com",
                "event": "upload",
                "messageId": "msg-large-001",
                "properties": big_props,
            }
        ]
        patcher, _ = _celery_mock()
        with patcher:
            resp = client.post(
                USAGE_URL,
                json={"events": events},
                headers={"X-API-Key": raw_key},
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["accepted"] == 1
        assert body["skipped"] == 0

        # Row exists with truncated properties
        row = db.query(UsageEvent).first()
        assert row is not None
        # Properties should be empty/truncated (not the original 17KB payload)
        assert row.properties is not None
        assert len(json.dumps(row.properties)) < 17 * 1024


class TestUsageIngestCeleryEnqueue:
    """AC7 — accepted events enqueued to correct task name with correct args."""

    def test_send_task_called_with_expected_args(self, client: TestClient, db: Session):
        org = _make_org(db)
        raw_key, _ = _make_api_key(db, org.id)
        event = _track_event("msg-enq-001", "alice@example.com")

        mock_app = MagicMock()
        mock_app.send_task.return_value.id = "task-123"

        with patch(_CELERY_PATCH, return_value=mock_app):
            resp = client.post(
                USAGE_URL,
                json={"events": [event]},
                headers={"X-API-Key": raw_key},
            )

        assert resp.status_code == 202
        assert mock_app.send_task.call_count == 1

        call_args = mock_app.send_task.call_args
        task_name = call_args[0][0]
        assert task_name == "src.tasks.usage_metrics.process_usage_event"

        # Verify positional args: [org_id, email, event_type, event_name, occurred_at_iso, external_event_id, properties]
        args = call_args[1]["args"] if "args" in call_args[1] else call_args[0][1]
        assert args[0] == org.id                   # org_id
        assert args[1] == "alice@example.com"       # customer_email
        assert args[2] == "track"                   # event_type
        assert args[3] == "login"                   # event_name (from "event" field)
        assert isinstance(args[4], str)             # occurred_at_iso (ISO-8601 string)
        assert args[5] == "msg-enq-001"             # external_event_id
        assert isinstance(args[6], dict)            # properties
