"""
snapshot-trend-columns aspect (usage-trend-automation-trigger, M3) — the
ordering fix: a ``customer_usage_history`` snapshot row for a given day must
carry the trend state/pct AS CLASSIFIED on that run, not the previous
cycle's stale value.

AC references: docs/planning/usage-trend-automation-trigger/
snapshot-trend-columns/spec.md AC3, AC4.

Self-contained SQLite engine + fixtures — same pattern as
test_usage_trend_wiring.py (each wiring test file in this repo owns its own
engine rather than sharing the module-level conftest one).

Why every fixture below seeds a customer whose classified state CHANGES on
the run under test: the snapshot payload dict is built at
usage_metrics.py:563, before trend classification runs at :586-592. Adding
`"usage_trend_state": row.usage_trend_state, "usage_trend_pct":
row.usage_trend_pct` directly to that literal captures the PREVIOUS cycle's
value, not this run's. A customer whose state is unchanged this run cannot
tell that naive implementation apart from the fix — the stale value and the
fresh value are identical — so these tests are worthless unless they force
a real transition and check the two values line up anyway.
"""
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, CustomerUsage, CustomerUsageHistory, Organization, UsageEvent

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


def _make_org(db: Session, name: str = "SnapshotTrendCorp") -> Organization:
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


def _seed_events(db: Session, org_id: int, email: str, reference: datetime, day_offsets) -> None:
    for i, offset in enumerate(day_offsets):
        db.add(UsageEvent(
            organization_id=org_id, customer_email=email,
            event_type="track", event_name="feat-a",
            external_event_id=f"evt-{email}-{offset}-{i}",
            occurred_at=reference - timedelta(days=offset),
            received_at=reference,
        ))
    db.commit()


def _reload(um):
    import importlib
    importlib.reload(um)
    return um


def _get_history_row(db: Session, org_id: int, email: str, snapshot_date: "date") -> CustomerUsageHistory:
    return (
        db.query(CustomerUsageHistory)
        .filter(
            CustomerUsageHistory.organization_id == org_id,
            CustomerUsageHistory.customer_email == email,
            CustomerUsageHistory.snapshot_date == snapshot_date,
        )
        .one()
    )


# ---------------------------------------------------------------------------
# AC3 — snapshot row's usage_trend_state/pct equal customer_usage's, for the
# same run, even (especially) when the classified state CHANGES this run.
# ---------------------------------------------------------------------------


class TestSnapshotRecordsPostClassificationState:
    def test_snapshot_state_matches_rollup_state_when_state_changes(self, db):
        """Stored state is 'stable'; this run reclassifies to 'declining'.
        The snapshot row for today must carry 'declining', not the stale
        'stable' the naive :563-literal fix would capture."""
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "transitioning@example.com"
        now = datetime(2026, 7, 15, 9, 0, 0)
        today = now.date()

        # In-band baseline (age 13 days): active_days_14d=12.
        _make_history(db, org.id, email, today - timedelta(days=13), 12)

        # Current active_days_14d re-derives to 6 via 6 distinct recent
        # days -> pct = (6-12)/12*100 = -50.0 -> declining.
        _seed_events(db, org.id, email, now, range(6))

        rollup = CustomerUsage(
            organization_id=org.id, customer_email=email,
            last_active_at=now, usage_score=50,
            active_days_7d=6, active_days_14d=6, active_days_30d=6,
            # Stored BEFORE this run — the value the naive :563 literal
            # would (wrongly) snapshot.
            usage_trend_state="stable",
            usage_trend_pct=0.0,
        )
        db.add(rollup)
        db.commit()

        with patch.object(um, "get_db_session", _fake_db_session), \
                patch.object(um, "datetime") as mock_dt:
            mock_dt.utcnow.return_value = now
            um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)
        assert rollup.usage_trend_state == "declining", (
            "fixture must actually transition this run, or this test "
            "cannot distinguish the fix from the naive implementation"
        )

        history_row = _get_history_row(db, org.id, email, today)
        assert history_row.usage_trend_state == rollup.usage_trend_state == "declining"
        assert history_row.usage_trend_pct == rollup.usage_trend_pct == -50.0

    def test_snapshot_state_matches_for_non_transitioning_customer_too(self, db):
        """Key-uniformity check: a customer whose state does NOT change
        this run must still get a non-NULL snapshot state — the trend keys
        are set unconditionally after classification, not only on the
        transition path (bulk_insert_mappings silently omits any key
        missing from a given dict rather than erroring)."""
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "steady@example.com"
        now = datetime(2026, 7, 15, 9, 0, 0)
        today = now.date()

        _make_history(db, org.id, email, today - timedelta(days=13), 12)
        _seed_events(db, org.id, email, now, range(12))

        rollup = CustomerUsage(
            organization_id=org.id, customer_email=email,
            last_active_at=now, usage_score=50,
            active_days_7d=7, active_days_14d=12, active_days_30d=12,
            usage_trend_state="stable",
            usage_trend_pct=0.0,
        )
        db.add(rollup)
        db.commit()

        with patch.object(um, "get_db_session", _fake_db_session), \
                patch.object(um, "datetime") as mock_dt:
            mock_dt.utcnow.return_value = now
            um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)
        assert rollup.usage_trend_state == "stable"

        history_row = _get_history_row(db, org.id, email, today)
        assert history_row.usage_trend_state == "stable"
        assert history_row.usage_trend_pct == 0.0


# ---------------------------------------------------------------------------
# AC4 — a customer transitioning on day N has day N's snapshot carrying the
# NEW state, and day N-1's snapshot carrying the OLD one.
# ---------------------------------------------------------------------------


class TestSnapshotAcrossTransitionDay:
    def test_day_n_minus_1_keeps_old_state_day_n_gets_new_state(self, db):
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "two_day_transition@example.com"
        day_n_minus_1 = datetime(2026, 7, 1, 9, 0, 0)
        # 13 days later: the day_n_minus_1 run's OWN auto-written snapshot
        # (dated day_n_minus_1) lands at age 13 for day N's baseline lookup
        # — squarely in the [12, 16] band — while the originally-seeded
        # history row (age 13 on day N-1) ages out to 26 by day N.
        day_n = day_n_minus_1 + timedelta(days=13)

        # Pre-existing baseline for day N-1's own run: age 13, value 12.
        _make_history(
            db, org.id, email, day_n_minus_1.date() - timedelta(days=13), 12,
        )

        # 12 distinct active days ending on day_n_minus_1 -> active_days_14d
        # == 12 on day N-1 (matches baseline -> pct 0.0 -> 'stable').
        _seed_events(db, org.id, email, day_n_minus_1, range(12))

        rollup = CustomerUsage(
            organization_id=org.id, customer_email=email,
            last_active_at=day_n_minus_1, usage_score=50,
            active_days_7d=7, active_days_14d=12, active_days_30d=12,
            usage_trend_state="insufficient_history",
            usage_trend_pct=None,
        )
        db.add(rollup)
        db.commit()

        # --- Run 1: day N-1 ---
        with patch.object(um, "get_db_session", _fake_db_session), \
                patch.object(um, "datetime") as mock_dt:
            mock_dt.utcnow.return_value = day_n_minus_1
            um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)
        assert rollup.usage_trend_state == "stable", (
            "fixture setup: day N-1 must classify to a real (non-"
            "insufficient-history) state so the day N transition is "
            "unambiguous"
        )
        old_state_row = _get_history_row(db, org.id, email, day_n_minus_1.date())
        assert old_state_row.usage_trend_state == "stable"

        # --- Run 2: day N. By day N, only 2 of the 12 seeded events are
        # still inside the (now-shifted) 14-day window (cutoff = day N - 14
        # = day N-1 - 1, so only the k=0 and k=1 offsets survive) ->
        # active_days_14d collapses from 12 to 2, against the baseline of
        # 12 resolved from day N-1's own snapshot -> pct =
        # (2-12)/12*100 = -83.33 -> sharp_decline. A real state transition,
        # distinct from 'stable'.
        with patch.object(um, "get_db_session", _fake_db_session), \
                patch.object(um, "datetime") as mock_dt:
            mock_dt.utcnow.return_value = day_n
            um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)
        assert rollup.usage_trend_state == "sharp_decline", (
            "fixture setup: day N must actually transition this run, or "
            "this test cannot distinguish the fix from the naive "
            "implementation"
        )

        new_state_row = _get_history_row(db, org.id, email, day_n.date())
        assert new_state_row.usage_trend_state == "sharp_decline"
        assert new_state_row.usage_trend_pct == -83.33

        # Day N-1's row (AC4's "day N-1's snapshot carrying the old state")
        # must be untouched by day N's run.
        old_state_row_after = _get_history_row(db, org.id, email, day_n_minus_1.date())
        assert old_state_row_after.usage_trend_state == "stable"

        assert old_state_row_after.usage_trend_state != new_state_row.usage_trend_state
