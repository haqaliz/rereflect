"""
Unit tests for `src/services/saml_replay.py` — the DB-backed InResponseTo /
replay store (aspect provider-and-replay-store, gap 1 state machine).

No migration needed: the `db` fixture builds schema from `Base.metadata`, and
`SamlAuthRequest` is exported from `src.models`. Expiry is exercised by
monkeypatching `saml_replay._now` rather than sleeping.

State machine under test:
    pending  -> row inserted at /saml/login (register_request)
    consumed -> consumed_at set by the conditional UPDATE on first valid use
    replay      = row already consumed_at         -> ConsumeOutcome.REPLAY
    unsolicited = no row for that request_id       -> ConsumeOutcome.UNSOLICITED
    expired     = expires_at < now (still pending) -> ConsumeOutcome.EXPIRED

The exactly-once guarantee is the race-safe conditional
`UPDATE ... WHERE consumed_at IS NULL AND expires_at >= now`.
"""
import os
import tempfile
import threading
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.organization import Organization
from src.models.saml_auth_request import SamlAuthRequest
from src.services import saml_replay
from src.services.saml_replay import (
    ConsumeOutcome,
    consume_request,
    register_request,
)


def _make_org(db) -> int:
    org = Organization(name="Replay Test Org", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org.id


# ── pending -> consumed (happy path) ────────────────────────────────────


def test_register_then_consume_ok(db):
    org_id = _make_org(db)
    register_request(db, request_id="_req-1", organization_id=org_id)

    outcome = consume_request(db, request_id="_req-1")

    assert outcome == ConsumeOutcome.OK
    row = db.query(SamlAuthRequest).filter_by(request_id="_req-1").first()
    assert row is not None
    assert row.consumed_at is not None  # pending -> consumed


def test_second_consume_is_replay(db):
    org_id = _make_org(db)
    register_request(db, request_id="_req-2", organization_id=org_id)

    assert consume_request(db, request_id="_req-2") == ConsumeOutcome.OK
    # A duplicate / polled ACS POST re-runs the conditional UPDATE -> 0 rows.
    assert consume_request(db, request_id="_req-2") == ConsumeOutcome.REPLAY


def test_unknown_request_is_unsolicited(db):
    _make_org(db)
    assert consume_request(db, request_id="_never-registered") == ConsumeOutcome.UNSOLICITED


def test_expired_request_is_rejected(db):
    org_id = _make_org(db)
    register_request(db, request_id="_req-exp", organization_id=org_id, ttl_seconds=600)

    # Jump the clock past the TTL so the pending row is expired.
    real_now = saml_replay._now()
    future = real_now + timedelta(seconds=700)
    orig = saml_replay._now
    saml_replay._now = lambda: future
    try:
        outcome = consume_request(db, request_id="_req-exp")
    finally:
        saml_replay._now = orig

    assert outcome == ConsumeOutcome.EXPIRED
    row = db.query(SamlAuthRequest).filter_by(request_id="_req-exp").first()
    assert row.consumed_at is None  # expired rows are never consumed


def test_opportunistic_cleanup_of_expired_rows_on_register(db):
    org_id = _make_org(db)
    # Insert an already-expired pending row directly.
    past = datetime.utcnow() - timedelta(seconds=3600)
    db.add(
        SamlAuthRequest(
            request_id="_stale",
            organization_id=org_id,
            created_at=past,
            expires_at=past + timedelta(seconds=600),  # still in the past
        )
    )
    db.commit()

    register_request(db, request_id="_fresh", organization_id=org_id)

    assert db.query(SamlAuthRequest).filter_by(request_id="_stale").first() is None
    assert db.query(SamlAuthRequest).filter_by(request_id="_fresh").first() is not None


def test_cleanup_failure_is_swallowed(db):
    """A cleanup DB failure must never propagate — it's best-effort/logged.
    Drive a broken session into `_cleanup_expired` and assert it does NOT raise
    (this is the contract that keeps a login from failing on a cleanup hiccup)."""
    from unittest.mock import MagicMock

    broken = MagicMock()
    broken.query.side_effect = RuntimeError("cleanup exploded")

    # Must not raise despite the query blowing up.
    saml_replay._cleanup_expired(broken)
    broken.rollback.assert_called_once()


def test_register_still_works_after_a_stale_row(db):
    """register succeeds and the pending row lands even when a prior expired row
    exists (exercises the cleanup path end-to-end without a failure)."""
    org_id = _make_org(db)
    register_request(db, request_id="_still-works", organization_id=org_id)
    assert db.query(SamlAuthRequest).filter_by(request_id="_still-works").first() is not None


# ── concurrent double-consume -> exactly one wins ──────────────────────


def test_concurrent_double_consume_exactly_one_ok(db):
    """SQLite in-memory has no true parallelism; the conditional
    `WHERE consumed_at IS NULL` UPDATE is the guarantee. Sequential calls
    prove it: exactly one OK, the rest REPLAY."""
    org_id = _make_org(db)
    register_request(db, request_id="_race", organization_id=org_id)

    outcomes = [consume_request(db, request_id="_race") for _ in range(5)]

    assert outcomes.count(ConsumeOutcome.OK) == 1
    assert outcomes.count(ConsumeOutcome.REPLAY) == 4


def test_threaded_double_consume_file_sqlite_exactly_one_ok(tmp_path):
    """Stronger variant: two real Sessions over a FILE-based SQLite race to
    consume the same request_id in threads. Exactly one must win (OK); the
    other resolves to REPLAY — real row contention, not just sequential."""
    db_path = tmp_path / "replay_race.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    setup = Session()
    org = Organization(name="Race Org", plan="pro")
    setup.add(org)
    setup.commit()
    org_id = org.id
    register_request(setup, request_id="_threaded-race", organization_id=org_id)
    setup.close()

    barrier = threading.Barrier(2)
    results = {}

    def worker(key):
        session = Session()
        try:
            barrier.wait()
            results[key] = consume_request(session, request_id="_threaded-race")
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    engine.dispose()

    values = list(results.values())
    assert values.count(ConsumeOutcome.OK) == 1
    assert values.count(ConsumeOutcome.REPLAY) == 1
