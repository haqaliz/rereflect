"""
Phase D — wiring tests for the trend-detection-and-health aspect:
trend classification/persistence inside `recompute_usage_scores`, sourced
from a single batched `customer_usage_history` lookback query
(`_load_trend_baselines`), and the extended health-refresh trigger (AC 12).

Self-contained SQLite engine + fixtures, same pattern as
test_usage_metrics.py (each wiring test file in this repo owns its own
engine rather than sharing the module-level conftest one).

AC references are to docs/planning/usage-trend-churn-signal/
trend-detection-and-health/spec.md.
"""
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, CustomerUsage, CustomerUsageHistory, Organization

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


@contextmanager
def _fake_db_session():
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
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture()
def db() -> Session:
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_org(db: Session, name: str = "TrendCorp") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_history(
    db: Session, org_id: int, email: str, snapshot_date: "date", active_days_14d,
) -> CustomerUsageHistory:
    row = CustomerUsageHistory(
        organization_id=org_id,
        customer_email=email,
        snapshot_date=snapshot_date,
        active_days_14d=active_days_14d,
    )
    db.add(row)
    db.commit()
    return row


def _reload(um):
    import importlib
    importlib.reload(um)
    return um


# ---------------------------------------------------------------------------
# AC 1, 2 — nearest-in-band lookback exercised through the real wiring
# ---------------------------------------------------------------------------


class TestTrendWiredThroughBatchedLookback:
    def test_nearest_in_band_snapshot_drives_persisted_trend(self, db):
        """
        Baseline snapshot 13 days back (active_days_14d=12); current
        active_days_14d re-derives to 6 (via seeded UsageEvent rows) ->
        pct = (6-12)/12*100 = -50.0 -> declining. Snapshots at 10 and 20
        days back are present too (out of band) to prove they're ignored.
        """
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "declining@example.com"
        today = datetime.utcnow().date()

        _make_history(db, org.id, email, today - timedelta(days=10), 999)  # out of band
        _make_history(db, org.id, email, today - timedelta(days=13), 12)   # IN BAND — used
        _make_history(db, org.id, email, today - timedelta(days=20), 999)  # out of band

        # 6 distinct active days within the last 14 days -> active_days_14d == 6
        for day in range(6):
            from src.models import UsageEvent
            db.add(UsageEvent(
                organization_id=org.id, customer_email=email,
                event_type="track", event_name="feat-a",
                external_event_id=f"evt-decl-{day}",
                occurred_at=datetime.utcnow() - timedelta(days=day),
                received_at=datetime.utcnow(),
            ))
        db.commit()

        rollup = CustomerUsage(
            organization_id=org.id, customer_email=email,
            last_active_at=datetime.utcnow(), usage_score=50,
            active_days_7d=6, active_days_14d=6, active_days_30d=6,
        )
        db.add(rollup)
        db.commit()

        with patch.object(um, "get_db_session", _fake_db_session):
            um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)
        assert rollup.usage_trend_state == "declining"
        assert rollup.usage_trend_pct == -50.0

    def test_no_in_band_snapshot_yields_insufficient_history(self, db):
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "noband@example.com"
        today = datetime.utcnow().date()

        _make_history(db, org.id, email, today - timedelta(days=10), 20)
        _make_history(db, org.id, email, today - timedelta(days=20), 20)

        rollup = CustomerUsage(
            organization_id=org.id, customer_email=email,
            last_active_at=datetime.utcnow(), usage_score=50,
            active_days_7d=0, active_days_14d=5, active_days_30d=5,
        )
        db.add(rollup)
        db.commit()

        with patch.object(um, "get_db_session", _fake_db_session):
            um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)
        assert rollup.usage_trend_state == "insufficient_history"
        assert rollup.usage_trend_pct is None

    def test_lookback_query_is_batched_not_per_row(self, db):
        """
        Not N+1: the customer_usage_history lookback is one SELECT scoped to
        the whole scanned population, independent of customer count. Asserts
        exactly one SELECT against customer_usage_history regardless of how
        many customers are scanned.
        """
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        today = datetime.utcnow().date()
        for i in range(15):
            email = f"batch{i}@example.com"
            _make_history(db, org.id, email, today - timedelta(days=13), 8)
            db.add(CustomerUsage(
                organization_id=org.id, customer_email=email,
                usage_score=50, active_days_14d=8,
                last_active_at=datetime.utcnow(),
            ))
        db.commit()

        statements = []

        def _counter(conn, cursor, statement, parameters, context, executemany):
            # Narrow to the trend-lookback SELECT specifically (it's the only
            # SELECT against this table that reads active_days_14d) — the
            # snapshot-write path also touches customer_usage_history (its
            # idempotency-check SELECT, and its bulk INSERT whose column
            # list happens to mention active_days_14d too), but both are out
            # of scope for this assertion.
            normalized = statement.strip().upper()
            if (
                normalized.startswith("SELECT")
                and "customer_usage_history" in statement
                and "active_days_14d" in statement
            ):
                statements.append(statement)

        event.listen(_ENGINE, "before_cursor_execute", _counter)
        try:
            with patch.object(um, "get_db_session", _fake_db_session):
                um.recompute_usage_scores()
        finally:
            event.remove(_ENGINE, "before_cursor_execute", _counter)

        assert len(statements) == 1, (
            f"expected exactly one batched trend-lookback SELECT against "
            f"customer_usage_history for 15 customers, got {len(statements)}"
        )


# ---------------------------------------------------------------------------
# AC 12 — trend-state transition triggers health refresh even when the
# usage_score itself moves < _HEALTH_RECOMPUTE_DELTA (or not at all).
# ---------------------------------------------------------------------------


class TestTrendTransitionTriggersHealthRefresh:
    def test_health_refresh_called_when_trend_changes_but_score_does_not(self, db):
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "trend_only_transition@example.com"
        today = datetime.utcnow().date()

        # In-band baseline that will classify as `declining` for a rollup
        # whose usage_score does NOT change on this run (windows already
        # match reality, so compute_usage_score(now) == stored usage_score).
        # baseline=12, current=6 -> pct = (6-12)/12*100 = -50.0 -> declining.
        _make_history(db, org.id, email, today - timedelta(days=13), 12)

        for day in range(6):
            from src.models import UsageEvent
            db.add(UsageEvent(
                organization_id=org.id, customer_email=email,
                event_type="track", event_name="feat-a",
                external_event_id=f"evt-fixed-{day}",
                occurred_at=datetime.utcnow() - timedelta(days=day),
                received_at=datetime.utcnow(),
            ))
        db.commit()

        from src.services.usage_score_service import compute_usage_score

        rollup = CustomerUsage(
            organization_id=org.id, customer_email=email,
            last_active_at=datetime.utcnow(),
            active_days_7d=6, active_days_14d=6, active_days_30d=6,
            distinct_feature_count=1,
            usage_trend_state="stable",  # starts stable -> should transition to declining
        )
        rollup.usage_score = compute_usage_score(rollup)
        db.add(rollup)
        db.commit()
        score_before = rollup.usage_score

        health_mock = MagicMock()
        sys.modules["src.services.health_score_service"] = health_mock
        try:
            with patch.object(um, "get_db_session", _fake_db_session):
                um.recompute_usage_scores()
        finally:
            sys.modules.pop("src.services.health_score_service", None)

        db.expire(rollup)
        db.refresh(rollup)

        assert rollup.usage_score == score_before, (
            "fixture must hold usage_score steady so the health-refresh "
            "trigger is exercised purely by the trend transition"
        )
        assert rollup.usage_trend_state == "declining"
        assert health_mock.update_customer_health.call_count >= 1
        call_args = health_mock.update_customer_health.call_args[0]
        assert call_args[0] == org.id
        assert call_args[1] == email

    def test_no_health_refresh_when_trend_and_score_both_unchanged(self, db):
        """Negative control: a steady customer with an unchanged trend state
        must NOT trigger update_customer_health from the trend path."""
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "steady_no_trigger@example.com"

        from src.services.usage_score_service import compute_usage_score

        rollup = CustomerUsage(
            organization_id=org.id, customer_email=email,
            last_active_at=datetime.utcnow(),
            active_days_7d=0, active_days_14d=0, active_days_30d=0,
            distinct_feature_count=0,
            usage_trend_state="insufficient_history",  # no history rows -> stays this way
        )
        rollup.usage_score = compute_usage_score(rollup)
        db.add(rollup)
        db.commit()

        health_mock = MagicMock()
        sys.modules["src.services.health_score_service"] = health_mock
        try:
            with patch.object(um, "get_db_session", _fake_db_session):
                um.recompute_usage_scores()
        finally:
            sys.modules.pop("src.services.health_score_service", None)

        assert health_mock.update_customer_health.call_count == 0


# ---------------------------------------------------------------------------
# AC 13 — idempotency with a fixed `now`
# ---------------------------------------------------------------------------


class TestTrendIdempotency:
    def test_running_twice_with_same_now_is_idempotent(self, db):
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "idempotent@example.com"
        fixed_now = datetime(2026, 7, 22, 9, 0, 0)
        today = fixed_now.date()

        _make_history(db, org.id, email, today - timedelta(days=13), 20)

        from src.services.usage_score_service import compute_usage_score

        rollup = CustomerUsage(
            organization_id=org.id, customer_email=email,
            last_active_at=fixed_now - timedelta(days=1),
            active_days_7d=6, active_days_14d=6, active_days_30d=6,
            distinct_feature_count=2,
        )
        rollup.usage_score = compute_usage_score(rollup, now=fixed_now)
        db.add(rollup)
        db.commit()

        health_mock = MagicMock()
        sys.modules["src.services.health_score_service"] = health_mock
        try:
            with patch.object(um, "get_db_session", _fake_db_session):
                with patch.object(um, "datetime") as mock_dt:
                    mock_dt.utcnow.return_value = fixed_now
                    um.recompute_usage_scores()

            db.expire(rollup)
            db.refresh(rollup)
            state_after_first = rollup.usage_trend_state
            pct_after_first = rollup.usage_trend_pct
            calls_after_first = health_mock.update_customer_health.call_count

            with patch.object(um, "get_db_session", _fake_db_session):
                with patch.object(um, "datetime") as mock_dt:
                    mock_dt.utcnow.return_value = fixed_now
                    um.recompute_usage_scores()
        finally:
            sys.modules.pop("src.services.health_score_service", None)

        db.expire(rollup)
        db.refresh(rollup)

        assert rollup.usage_trend_state == state_after_first
        assert rollup.usage_trend_pct == pct_after_first
        # No NEW health-refresh call on the second, no-op run.
        assert health_mock.update_customer_health.call_count == calls_after_first
