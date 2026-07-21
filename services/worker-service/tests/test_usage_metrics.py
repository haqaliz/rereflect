"""
TDD tests for the usage_metrics Celery task — Phase 3.

Acceptance criteria (from spec):
  AC1. process_usage_event upserts customer_usage (events_total increments,
       last_active_at advances, event_name added to distinct_features).
  AC2. Re-processing the same external_event_id does not double-count.
  AC5. process_usage_event calls update_customer_health exactly once.
  AC4. (Phase 4 test also here) Scheduled recompute lowers usage_score
       for a customer whose last_active_at has aged past recency thresholds.

Strategy: use an in-memory SQLite DB seeded with UsageEvent rows, injecting
a mock for src.services.health_score_service via sys.modules (matching the
pattern used by test_analysis_winback_integration.py).  The core logic is
tested via ``_do_process_usage_event`` (the extracted helper, not the Celery
wrapper), mirroring how analysis.py tests use ``_analyze_feedback_item``.
"""

import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# The conftest already stubs src.config + src.database in sys.modules before
# this file is imported. We override the get_db_session below for our tests.
from src.models import Base, Organization, UsageEvent, CustomerUsage


# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated from the conftest engine)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


@contextmanager
def _fake_db_session():
    """Thin context manager that yields a SQLite session (mirrors get_db_session)."""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _fresh_db():
    """Create all tables before each test and drop them after."""
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture()
def db() -> Session:
    """Return a plain SQLite session for fixture setup."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session) -> Organization:
    org = Organization(name="TestCorp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_event(
    db: Session,
    org_id: int,
    email: str = "alice@example.com",
    event_type: str = "track",
    event_name: str = "clicked_feature_a",
    external_event_id: str = "msg-001",
    days_ago: float = 0,
) -> UsageEvent:
    occurred_at = datetime.utcnow() - timedelta(days=days_ago)
    ev = UsageEvent(
        organization_id=org_id,
        customer_email=email,
        event_type=event_type,
        event_name=event_name,
        external_event_id=external_event_id,
        occurred_at=occurred_at,
        received_at=datetime.utcnow(),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _run_impl(
    org_id: int,
    email,
    external_event_id: str,
    event_type: str = "track",
    event_name: str = "clicked_feature_a",
    health_mock=None,
) -> tuple:
    """
    Call _do_process_usage_event with:
      - get_db_session patched to use the test SQLite DB
      - src.services.health_score_service injected as health_mock
    """
    if health_mock is None:
        health_mock = MagicMock()

    sys.modules["src.services.health_score_service"] = health_mock

    try:
        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        with patch.object(um, "get_db_session", _fake_db_session):
            result = um._do_process_usage_event(
                org_id=org_id,
                customer_email=email,
                event_type=event_type,
                event_name=event_name,
                occurred_at_iso=datetime.utcnow().isoformat(),
                external_event_id=external_event_id,
                properties=None,
            )
        return result, health_mock
    finally:
        sys.modules.pop("src.services.health_score_service", None)


def _get_rollup(db: Session, org_id: int, email: str):
    return (
        db.query(CustomerUsage)
        .filter_by(organization_id=org_id, customer_email=email)
        .first()
    )


# ---------------------------------------------------------------------------
# AC1: Upsert increments events_total, advances last_active_at
# ---------------------------------------------------------------------------


class TestProcessUsageEventUpsert:
    def test_creates_rollup_on_first_event(self, db):
        """First event → customer_usage row created with events_total=1."""
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-1", days_ago=1)

        result, _ = _run_impl(org.id, "alice@example.com", "evt-1")

        assert result["status"] == "ok"
        assert result["events_total"] == 1

        rollup = _get_rollup(db, org.id, "alice@example.com")
        assert rollup is not None
        assert rollup.events_total == 1

    def test_second_event_increments_events_total(self, db):
        """Second distinct event → events_total = 2."""
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-1", event_name="feat-a", days_ago=2)
        _make_event(db, org.id, external_event_id="evt-2", event_name="feat-b", days_ago=1)

        _run_impl(org.id, "alice@example.com", "evt-1", event_name="feat-a")
        result, _ = _run_impl(org.id, "alice@example.com", "evt-2", event_name="feat-b")

        assert result["events_total"] == 2
        rollup = _get_rollup(db, org.id, "alice@example.com")
        assert rollup.events_total == 2

    def test_last_active_at_is_set(self, db):
        """last_active_at is populated from the most recent event's occurred_at."""
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-1", days_ago=0.5)

        _run_impl(org.id, "alice@example.com", "evt-1")

        rollup = _get_rollup(db, org.id, "alice@example.com")
        assert rollup.last_active_at is not None

    def test_distinct_features_populated(self, db):
        """event_name is tracked in distinct_features."""
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-1", event_name="feature_x", days_ago=1)

        _run_impl(org.id, "alice@example.com", "evt-1", event_name="feature_x")

        rollup = _get_rollup(db, org.id, "alice@example.com")
        assert "feature_x" in rollup.distinct_features
        assert rollup.distinct_feature_count == 1

    def test_usage_score_is_set(self, db):
        """usage_score is populated (0-100) after processing."""
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-1", days_ago=1)

        _run_impl(org.id, "alice@example.com", "evt-1")

        rollup = _get_rollup(db, org.id, "alice@example.com")
        assert 0 <= rollup.usage_score <= 100

    def test_skips_when_no_customer_email(self, db):
        """Task returns skipped when customer_email is None."""
        org = _make_org(db)

        result, _ = _run_impl(org.id, None, "evt-no-email")

        assert result["status"] == "skipped"
        assert result["reason"] == "no_customer_email"

    def test_skips_when_raw_event_not_found(self, db):
        """Task returns skipped when raw event not in DB."""
        org = _make_org(db)

        result, _ = _run_impl(org.id, "alice@example.com", "nonexistent-evt")

        assert result["status"] == "skipped"
        assert result["reason"] == "event_not_found"

    def test_cross_tenant_isolation(self, db):
        """Event for org1 does not appear in org2's rollup."""
        org1 = _make_org(db)
        org2 = Organization(name="OtherCorp", plan="pro")
        db.add(org2)
        db.commit()
        db.refresh(org2)

        _make_event(db, org1.id, external_event_id="evt-org1", days_ago=1)

        _run_impl(org1.id, "alice@example.com", "evt-org1")

        assert _get_rollup(db, org2.id, "alice@example.com") is None
        assert _get_rollup(db, org1.id, "alice@example.com") is not None


# ---------------------------------------------------------------------------
# AC2: Idempotency — re-processing same external_event_id does not double-count
# ---------------------------------------------------------------------------


class TestProcessUsageEventIdempotency:
    def test_reprocessing_same_event_does_not_double_count(self, db):
        """
        Running _do_process_usage_event twice with the same external_event_id
        must NOT result in events_total > 1.
        """
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-dup", event_name="feat-a", days_ago=1)

        # Process twice
        _run_impl(org.id, "alice@example.com", "evt-dup", event_name="feat-a")
        result, _ = _run_impl(org.id, "alice@example.com", "evt-dup", event_name="feat-a")

        assert result["events_total"] == 1  # still one raw event in the DB
        rollup = _get_rollup(db, org.id, "alice@example.com")
        assert rollup.events_total == 1
        assert rollup.distinct_feature_count == 1

    def test_reprocessing_does_not_duplicate_features(self, db):
        """distinct_features has no duplicates after multiple re-processes."""
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-1", event_name="feat-a", days_ago=1)

        for _ in range(3):
            _run_impl(org.id, "alice@example.com", "evt-1", event_name="feat-a")

        rollup = _get_rollup(db, org.id, "alice@example.com")
        assert rollup.distinct_features.count("feat-a") == 1
        assert rollup.distinct_feature_count == 1


# ---------------------------------------------------------------------------
# AC5: update_customer_health called exactly once per processed event
# ---------------------------------------------------------------------------


class TestProcessUsageEventHealthRecompute:
    def test_update_customer_health_called_once(self, db):
        """update_customer_health is called exactly once per task run."""
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-h", days_ago=1)

        health_mock = MagicMock()

        _run_impl(org.id, "alice@example.com", "evt-h", health_mock=health_mock)

        assert health_mock.update_customer_health.call_count == 1
        call_args = health_mock.update_customer_health.call_args[0]
        assert call_args[0] == org.id
        assert call_args[1] == "alice@example.com"

    def test_health_import_error_does_not_fail_task(self, db):
        """If health_score_service is unavailable, the task still succeeds."""
        org = _make_org(db)
        _make_event(db, org.id, external_event_id="evt-no-health", days_ago=1)

        # Remove any previously cached module to force ImportError path
        sys.modules.pop("src.services.health_score_service", None)

        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        with patch.object(um, "get_db_session", _fake_db_session):
            result = um._do_process_usage_event(
                org_id=org.id,
                customer_email="alice@example.com",
                event_type="track",
                event_name="feat-a",
                occurred_at_iso=datetime.utcnow().isoformat(),
                external_event_id="evt-no-health",
                properties=None,
            )

        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Phase 4 / AC4: Scheduled recompute applies recency decay
# ---------------------------------------------------------------------------


class TestRecomputeUsageScores:
    def test_stale_rollup_score_drops_on_recompute(self, db):
        """
        A customer who WAS active — high active_days_30d/7d and login counts
        from a previous burst of usage — but whose last_active_at is now 50
        days ago and who has NO usage_event rows in the last 30 days, must
        have their rolling-window fields re-derived to zero (not frozen at
        their stale high values) and their usage_score drop below 40.

        The fixture deliberately does NOT hand-set the window fields to 0 —
        that would presuppose the re-windowing this test exists to prove.
        """
        org = _make_org(db)
        # Create a CustomerUsage row reflecting a customer who WAS active —
        # no usage_event rows back it (none within the 30d window, none at all).
        rollup = CustomerUsage(
            organization_id=org.id,
            customer_email="bob@example.com",
            last_active_at=datetime.utcnow() - timedelta(days=50),  # very stale
            active_days_30d=25,
            active_days_7d=6,
            distinct_feature_count=1,
            distinct_features=["feat-x"],
            login_count_7d=9,
            login_count_30d=40,
            events_total=5,
            usage_score=75,  # artificially high — should drop on recompute
            first_seen_at=datetime.utcnow() - timedelta(days=100),
        )
        db.add(rollup)
        db.commit()
        db.refresh(rollup)
        old_score = rollup.usage_score

        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        with patch.object(um, "get_db_session", _fake_db_session):
            result = um.recompute_usage_scores()

        assert result["total"] >= 1
        assert result["updated"] >= 1

        db.expire(rollup)
        db.refresh(rollup)
        assert rollup.active_days_30d == 0, (
            f"active_days_30d frozen at stale value: got {rollup.active_days_30d}"
        )
        assert rollup.active_days_7d == 0, (
            f"active_days_7d frozen at stale value: got {rollup.active_days_7d}"
        )
        assert rollup.login_count_30d == 0, (
            f"login_count_30d frozen at stale value: got {rollup.login_count_30d}"
        )
        assert rollup.login_count_7d == 0, (
            f"login_count_7d frozen at stale value: got {rollup.login_count_7d}"
        )
        assert rollup.usage_score < old_score, (
            f"Score should have dropped from {old_score}, got {rollup.usage_score}"
        )
        assert rollup.usage_score < 40, f"Stale score expected <40, got {rollup.usage_score}"

    def test_lifetime_aggregates_survive_recompute(self, db):
        """
        Lifetime aggregates — events_total, first_seen_at, distinct_features —
        must NOT change when recompute_usage_scores re-derives the rolling-
        window fields. This is the guard against the bounded-read trap: the
        window re-derivation is meant to read only the last 30 days of
        usage_event rows, and if that bounded dict were ever written back in
        place of the full rollup, events_total would collapse to the 30-day
        count, first_seen_at would jump forward, and long-tail
        distinct_features would vanish. first_seen_at is unrecoverable once
        overwritten, so this must hold before any re-derivation logic exists.
        """
        org = _make_org(db)
        # Spread events across ~200 days so the lifetime aggregates (5 total
        # events, 5 distinct features, first_seen_at ~200 days back) are
        # clearly distinguishable from anything a 30-day-bounded read would see.
        for i in range(5):
            _make_event(
                db, org.id,
                external_event_id=f"evt-lifetime-{i}",
                event_name=f"feat-{i}",
                days_ago=200 - i * 40,  # 200, 160, 120, 80, 40 days ago
            )
        # Build the rollup via the real upsert path (full-history read).
        _run_impl(org.id, "alice@example.com", "evt-lifetime-4", event_name="feat-4")

        rollup = _get_rollup(db, org.id, "alice@example.com")
        assert rollup.events_total == 5
        assert len(rollup.distinct_features) == 5
        events_total_before = rollup.events_total
        first_seen_at_before = rollup.first_seen_at
        distinct_features_before = list(rollup.distinct_features)

        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        with patch.object(um, "get_db_session", _fake_db_session):
            um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)

        assert rollup.events_total == events_total_before, (
            f"events_total truncated by bounded window read: "
            f"expected {events_total_before}, got {rollup.events_total}"
        )
        assert rollup.first_seen_at == first_seen_at_before, (
            f"first_seen_at overwritten by bounded window read: "
            f"expected {first_seen_at_before}, got {rollup.first_seen_at}"
        )
        assert list(rollup.distinct_features) == distinct_features_before, (
            f"distinct_features truncated by bounded window read: "
            f"expected {distinct_features_before}, got {rollup.distinct_features}"
        )

    def test_active_customer_windows_unchanged(self, db):
        """
        A customer with steady, CURRENT activity has identical window field
        values after a recompute_usage_scores run — no spurious churn for
        someone who is still engaged.

        The rollup's window fields are hand-set to exactly match the
        usage_event rows seeded below, so this test is meaningful both
        before re-derivation lands (fields are simply left alone) and after
        (fields are recomputed from real events but land on the same
        numbers).
        """
        org = _make_org(db)
        email = "carol@example.com"

        # 5 distinct days within the last 7 days (one event each).
        recent_days = [0, 1, 2, 3, 4]
        # 15 more distinct days within the 30-day window but older than 7
        # days (one event each) -> 20 distinct active days total in 30d.
        older_days = list(range(8, 23))

        for day in recent_days + older_days:
            _make_event(
                db, org.id,
                email=email,
                external_event_id=f"evt-active-{day}",
                event_name="feat-a",
                days_ago=day,
            )

        rollup = CustomerUsage(
            organization_id=org.id,
            customer_email=email,
            last_active_at=datetime.utcnow(),
            active_days_30d=20,
            active_days_7d=5,
            distinct_feature_count=1,
            distinct_features=["feat-a"],
            login_count_7d=5,
            login_count_30d=20,
            events_total=20,
            usage_score=50,
            first_seen_at=datetime.utcnow() - timedelta(days=max(older_days)),
        )
        db.add(rollup)
        db.commit()
        db.refresh(rollup)

        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        with patch.object(um, "get_db_session", _fake_db_session):
            um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)

        assert rollup.active_days_7d == 5
        assert rollup.active_days_30d == 20
        assert rollup.login_count_7d == 5
        assert rollup.login_count_30d == 20

    def test_recompute_is_idempotent(self, db):
        """
        Running recompute_usage_scores twice in a row must produce identical
        rollup values on the second pass as on the first — no drift from
        re-deriving the same underlying window on repeated runs.
        """
        org = _make_org(db)
        rollup = CustomerUsage(
            organization_id=org.id,
            customer_email="dave@example.com",
            last_active_at=datetime.utcnow() - timedelta(days=50),
            active_days_30d=25,
            active_days_7d=6,
            distinct_feature_count=1,
            distinct_features=["feat-x"],
            login_count_7d=9,
            login_count_30d=40,
            events_total=5,
            usage_score=75,
            first_seen_at=datetime.utcnow() - timedelta(days=100),
        )
        db.add(rollup)
        db.commit()
        db.refresh(rollup)

        def _snapshot():
            db.expire(rollup)
            db.refresh(rollup)
            return {
                "active_days_7d": rollup.active_days_7d,
                "active_days_30d": rollup.active_days_30d,
                "login_count_7d": rollup.login_count_7d,
                "login_count_30d": rollup.login_count_30d,
                "usage_score": rollup.usage_score,
                "events_total": rollup.events_total,
                "first_seen_at": rollup.first_seen_at,
                "distinct_features": list(rollup.distinct_features),
            }

        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        with patch.object(um, "get_db_session", _fake_db_session):
            um.recompute_usage_scores()
        snapshot_after_first = _snapshot()

        with patch.object(um, "get_db_session", _fake_db_session):
            um.recompute_usage_scores()
        snapshot_after_second = _snapshot()

        assert snapshot_after_second == snapshot_after_first, (
            f"recompute is not idempotent: first={snapshot_after_first} "
            f"second={snapshot_after_second}"
        )

    def test_fresh_rollup_score_unchanged_on_recompute(self, db):
        """
        A customer who was very recently active and already has the correct
        score should NOT be marked as updated.

        The fixture is backed by real usage_event rows (not just hand-set
        window fields) so that window re-derivation is a genuine no-op —
        otherwise this would just be another instance of the honesty bug
        the RED test in this class exists to catch (see
        test_stale_rollup_score_drops_on_recompute).
        """
        from src.services.usage_score_service import compute_usage_score

        org = _make_org(db)
        email = "fresh@example.com"

        # 5 distinct days within the last 7 days (one event each).
        recent_days = [0, 1, 2, 3, 4]
        # 15 more distinct days within the 30-day window, kept well clear of
        # the 14-day cutoff (>=15 days ago) so active_days_14d == 5 with no
        # boundary-timing flakiness between the two utcnow() calls.
        older_days = list(range(15, 30))

        for day in recent_days + older_days:
            _make_event(
                db, org.id,
                email=email,
                external_event_id=f"evt-fresh-{day}",
                event_name="feat-a",
                days_ago=day,
            )

        rollup = CustomerUsage(
            organization_id=org.id,
            customer_email=email,
            last_active_at=datetime.utcnow() - timedelta(hours=6),
            active_days_30d=20,
            active_days_14d=5,
            active_days_7d=5,
            distinct_feature_count=1,
            distinct_features=["feat-a"],
            login_count_7d=5,
            login_count_30d=20,
            events_total=30,
            first_seen_at=datetime.utcnow() - timedelta(days=60),
        )
        # Pre-compute and store the correct score so nothing changes
        rollup.usage_score = compute_usage_score(rollup)
        db.add(rollup)
        db.commit()

        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        with patch.object(um, "get_db_session", _fake_db_session):
            result = um.recompute_usage_scores()

        assert result["updated"] == 0


# ---------------------------------------------------------------------------
# Critical: recompute_usage_scores must be a registered Celery task
# ---------------------------------------------------------------------------


class TestRecomputeUsageScoresCeleryRegistration:
    def test_recompute_usage_scores_is_registered_celery_task(self):
        """
        RED before fix: recompute_usage_scores is a plain function — not registered
        in celery_app.tasks — so beat raises NotRegistered at runtime.
        GREEN after fix: @shared_task(name=...) decorator registers it.

        Imports celery_app (which the conftest env supports via mocked src.config)
        and forces the task module to be (re)loaded so @shared_task decorators fire.
        """
        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)  # ensure @shared_task decorators have fired

        from src.celery_app import celery_app
        assert "src.tasks.usage_metrics.recompute_usage_scores" in celery_app.tasks, (
            "recompute_usage_scores is not registered as a Celery task; "
            "decorate it with @shared_task(name='src.tasks.usage_metrics.recompute_usage_scores')"
        )


# ---------------------------------------------------------------------------
# Important 1: SQLAlchemyError from _call_update_health must propagate
# ---------------------------------------------------------------------------


class TestCallUpdateHealthErrorPropagation:
    def test_sqlalchemy_error_propagates_not_swallowed(self):
        """
        RED before fix: bare except Exception swallows SQLAlchemyError, returns silently.
        GREEN after fix: only ImportError is swallowed; DB errors propagate for Celery retry.
        """
        from sqlalchemy.exc import SQLAlchemyError
        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        mock_health = MagicMock()
        mock_health.update_customer_health.side_effect = SQLAlchemyError("transient DB error")
        sys.modules["src.services.health_score_service"] = mock_health

        try:
            with pytest.raises(SQLAlchemyError):
                um._call_update_health(1, "test@example.com", None)
        finally:
            sys.modules.pop("src.services.health_score_service", None)
            importlib.reload(um)  # restore module to clean state

    def test_import_error_still_swallowed(self):
        """ImportError (partial-deploy) is still tolerated — no exception raised."""
        import importlib
        import src.tasks.usage_metrics as um
        importlib.reload(um)

        # Remove module so the import inside _call_update_health fails
        sys.modules.pop("src.services.health_score_service", None)

        try:
            # Should not raise — ImportError path is still swallowed
            um._call_update_health(1, "test@example.com", None)
        finally:
            importlib.reload(um)
