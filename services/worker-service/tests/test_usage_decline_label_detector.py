"""
TDD tests for usage_decline_label_detector.detect_usage_decline_labels
(worker-detector aspect — Phases 1-3 ONLY. Phase 4 (writes) and Phase 5
(wiring into recompute_usage_scores) are a separate, later task; a human
checkpoint is required after Phase 3, before any write path exists.)

Strategy (mirrors test_churn_suggestion_harvester.py:1-49): file-local
in-memory SQLite engine (not conftest's) + real ORM rows — no MagicMock for
the DB layer. A SQLAlchemy `event.listen(... "before_cursor_execute" ...)`
query-counter (mirrors backend-api's test_customers_tags_owner.py:121-135)
asserts the "no history query when mode=off" and "one batched query
regardless of customer count" properties directly, rather than trusting
return values.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, ChurnLabelSuggestion, CustomerUsage, CustomerUsageHistory, OrgAIConfig
from src.services.usage_decline_label_detector import detect_usage_decline_labels
from src.services.usage_decline_labels_core import QUALIFYING_STATE

# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated, file-local — not conftest's)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


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


# ---------------------------------------------------------------------------
# Query counter (mirrors backend-api tests/test_customers_tags_owner.py:121-135)
# ---------------------------------------------------------------------------


class _QueryCounter:
    """Counts SELECT statements issued against a given table name (matched
    case-insensitively against the lowercased SQL statement), while active.
    """

    def __init__(self, table_name: str):
        self.table_name = table_name.lower()
        self.statements: list[str] = []

    def _before(self, conn, cursor, statement, params, context, executemany):
        if f"from {self.table_name}" in statement.lower():
            self.statements.append(statement)

    def __enter__(self):
        event.listen(_ENGINE, "before_cursor_execute", self._before)
        return self

    def __exit__(self, exc_type, exc, tb):
        event.remove(_ENGINE, "before_cursor_execute", self._before)

    @property
    def count(self) -> int:
        return len(self.statements)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _org_config(
    db: Session,
    org_id: int = 1,
    mode: str | None = "active",
    sustain_days: int | None = None,
) -> OrgAIConfig:
    config = OrgAIConfig(
        organization_id=org_id,
        usage_churn_labels_mode=mode,
        usage_churn_label_config=(
            {"sustain_days": sustain_days} if sustain_days is not None else None
        ),
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _customer_usage(
    db: Session,
    org_id: int,
    email: str,
    *,
    last_active_at: datetime | None = None,
    trend_state: str = QUALIFYING_STATE,
) -> CustomerUsage:
    row = CustomerUsage(
        organization_id=org_id,
        customer_email=email,
        last_active_at=last_active_at,
        usage_trend_state=trend_state,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _history_rows(
    db: Session,
    org_id: int,
    email: str,
    *,
    end_date: date,
    num_days: int,
    trend_state: str = QUALIFYING_STATE,
) -> None:
    """Insert `num_days` calendar-consecutive rows ending at `end_date`
    (inclusive), all with the same trend_state — the "solid streak" shape.
    """
    for offset in range(num_days):
        snapshot_date = end_date - timedelta(days=offset)
        db.add(
            CustomerUsageHistory(
                organization_id=org_id,
                customer_email=email,
                snapshot_date=snapshot_date,
                usage_trend_state=trend_state,
                active_days_14d=2,
            )
        )
    db.commit()


TODAY = date(2026, 7, 23)


def _qualifying_customer(db: Session, org_id: int, email: str, sustain_days: int = 7) -> None:
    """A customer with a full sustain_days-length sharp_decline streak ending
    TODAY, and a non-null last_active_at (so it would be write-eligible once
    Phase 4 exists)."""
    _customer_usage(
        db, org_id, email,
        last_active_at=datetime(2026, 7, 10, 12, 0, 0),
        trend_state=QUALIFYING_STATE,
    )
    _history_rows(db, org_id, email, end_date=TODAY, num_days=sustain_days)


# ===========================================================================
# Phase 1 — detector skeleton + mode gate
# ===========================================================================


class TestModeGate:
    def test_mode_off_skips_and_performs_no_history_query(self, db):
        _org_config(db, org_id=1, mode="off")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        with _QueryCounter("customer_usage_history") as history_counter, \
             _QueryCounter("customer_usage") as customer_counter:
            result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "skipped"
        assert result["reason"] == "mode_off"
        assert history_counter.count == 0
        assert customer_counter.count == 0
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_no_org_ai_config_row_treated_as_off(self, db):
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        with _QueryCounter("customer_usage_history") as history_counter:
            result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "skipped"
        assert result["reason"] == "mode_off"
        assert history_counter.count == 0

    def test_null_mode_treated_as_off(self, db):
        _org_config(db, org_id=1, mode=None)

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "skipped"
        assert result["reason"] == "mode_off"

    def test_unrecognized_mode_treated_as_off(self, db):
        _org_config(db, org_id=1, mode="bogus_mode")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "skipped"
        assert result["reason"] == "mode_off"

    def test_mode_shadow_evaluates_fully_and_writes_zero_rows(self, db, caplog):
        _org_config(db, org_id=1, mode="shadow")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        with caplog.at_level(logging.INFO):
            result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "shadow"
        assert result["would_suggest"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_mode_active_computes_but_write_path_not_yet_implemented(self, db):
        """Phase 1-3: 'active' mode may compute + log, but writes come in
        Phase 4 (out of scope here) — so it must still write zero rows."""
        _org_config(db, org_id=1, mode="active")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "evaluated"
        assert result["qualifying"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_sustain_days_defaults_to_7_when_config_null(self, db):
        _org_config(db, org_id=1, mode="shadow", sustain_days=None)
        # Exactly 7 days qualifies under the default.
        _qualifying_customer(db, org_id=1, email="alice@example.com", sustain_days=7)

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["would_suggest"] == 1

    def test_sustain_days_honors_configured_value(self, db):
        _org_config(db, org_id=1, mode="shadow", sustain_days=3)
        _customer_usage(
            db, 1, "alice@example.com",
            last_active_at=datetime(2026, 7, 10),
            trend_state=QUALIFYING_STATE,
        )
        # Only 3 consecutive days — would NOT qualify under default 7, but
        # DOES qualify under the configured 3.
        _history_rows(db, 1, "alice@example.com", end_date=TODAY, num_days=3)

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["would_suggest"] == 1


# ===========================================================================
# Phase 2 — batched history load
# ===========================================================================


class TestBatchedHistoryLoad:
    def test_history_query_count_does_not_scale_with_customer_count(self, db):
        _org_config(db, org_id=1, mode="shadow")
        for i in range(50):
            _qualifying_customer(db, org_id=1, email=f"customer{i}@example.com")

        with _QueryCounter("customer_usage_history") as history_counter:
            result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["would_suggest"] == 50
        # A small constant, not one-per-customer: 50 customers must not
        # produce 50 history queries.
        assert history_counter.count <= 1, (
            f"expected <=1 history query for 50 customers, got "
            f"{history_counter.count}"
        )

    def test_history_query_count_constant_regardless_of_small_or_large_org(self, db):
        _org_config(db, org_id=1, mode="shadow")
        _qualifying_customer(db, org_id=1, email="solo@example.com")

        with _QueryCounter("customer_usage_history") as small_org_counter:
            detect_usage_decline_labels(1, db, today=TODAY)

        _org_config(db, org_id=2, mode="shadow")
        for i in range(50):
            _qualifying_customer(db, org_id=2, email=f"customer{i}@example.com")

        with _QueryCounter("customer_usage_history") as large_org_counter:
            detect_usage_decline_labels(2, db, today=TODAY)

        assert small_org_counter.count == large_org_counter.count

    def test_window_is_calendar_days_not_last_n_existing_rows(self, db):
        """A stale, already-ended streak from long before the current
        window must NOT be mistaken for a current one. If the query pulled
        "the last N existing rows" instead of filtering to the calendar
        window, a gap right before `today` would cause it to reach past the
        gap into this old block and incorrectly qualify a stale streak.
        """
        _org_config(db, org_id=1, mode="shadow", sustain_days=7)
        _customer_usage(
            db, 1, "alice@example.com",
            last_active_at=datetime(2026, 6, 1),
            trend_state=QUALIFYING_STATE,
        )
        # A solid 7-day streak that ENDED 20 days before `today` — well
        # outside the calendar window — followed by a gap covering the rest
        # of the days up to `today` (no rows at all near `today`).
        stale_streak_end = TODAY - timedelta(days=20)
        _history_rows(db, 1, "alice@example.com", end_date=stale_streak_end, num_days=7)

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["would_suggest"] == 0

    def test_gap_within_window_breaks_streak(self, db):
        """A single missing calendar day inside the sustain window must
        break the streak — proves the window is date-filtered, not just
        row-count-limited."""
        _org_config(db, org_id=1, mode="shadow", sustain_days=7)
        _customer_usage(
            db, 1, "alice@example.com",
            last_active_at=datetime(2026, 7, 10),
            trend_state=QUALIFYING_STATE,
        )
        # 7 rows ending today, but skip day TODAY-3 entirely (gap).
        for offset in range(7):
            if offset == 3:
                continue
            db.add(
                CustomerUsageHistory(
                    organization_id=1,
                    customer_email="alice@example.com",
                    snapshot_date=TODAY - timedelta(days=offset),
                    usage_trend_state=QUALIFYING_STATE,
                    active_days_14d=2,
                )
            )
        db.commit()

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["would_suggest"] == 0
