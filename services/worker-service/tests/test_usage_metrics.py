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
        A customer whose last_active_at is >30 days ago should have their
        usage_score lowered by recompute_usage_scores(), simulating no new events.
        """
        org = _make_org(db)
        # Create a CustomerUsage row with an artificially high (stale) score
        rollup = CustomerUsage(
            organization_id=org.id,
            customer_email="bob@example.com",
            last_active_at=datetime.utcnow() - timedelta(days=50),  # very stale
            active_days_30d=0,
            active_days_7d=0,
            distinct_feature_count=1,
            distinct_features=["feat-x"],
            login_count_7d=0,
            login_count_30d=0,
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
        assert rollup.usage_score < old_score, (
            f"Score should have dropped from {old_score}, got {rollup.usage_score}"
        )
        assert rollup.usage_score < 40, f"Stale score expected <40, got {rollup.usage_score}"

    def test_fresh_rollup_score_unchanged_on_recompute(self, db):
        """
        A customer who was very recently active and already has the correct
        score should NOT be marked as updated.
        """
        from src.services.usage_score_service import compute_usage_score

        org = _make_org(db)
        rollup = CustomerUsage(
            organization_id=org.id,
            customer_email="fresh@example.com",
            last_active_at=datetime.utcnow() - timedelta(hours=6),
            active_days_30d=20,
            active_days_7d=5,
            distinct_feature_count=5,
            distinct_features=["a", "b", "c", "d", "e"],
            login_count_7d=10,
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
