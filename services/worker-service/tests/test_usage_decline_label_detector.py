"""
TDD tests for usage_decline_label_detector.detect_usage_decline_labels
(worker-detector aspect — Phases 1-4. Phase 5 (wiring into
recompute_usage_scores) lives in test_usage_decline_detector_seam.py.)

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

from src.models import (
    Base,
    ChurnLabelSuggestion,
    CustomerChurnEvent,
    CustomerUsage,
    CustomerUsageHistory,
    OrgAIConfig,
)
from src.services.usage_decline_label_detector import (
    PER_RUN_SUGGESTION_CAP,
    detect_usage_decline_labels,
)
from src.services.usage_decline_labels_core import QUALIFYING_STATE, suggestion_key

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


def _trend_eligible_non_qualifying_customer(db: Session, org_id: int, email: str) -> None:
    """Trend-eligible (a real, non-'insufficient_history' current state) but
    does NOT have a qualifying streak — counts toward `eligible` but not
    `qualifying` in the M3b denominator/numerator."""
    _customer_usage(
        db, org_id, email,
        last_active_at=datetime(2026, 7, 10, 12, 0, 0),
        trend_state="stable",
    )


def _not_trend_eligible_customer(db: Session, org_id: int, email: str) -> None:
    """insufficient_history — excluded entirely from the M3b population."""
    _customer_usage(
        db, org_id, email,
        last_active_at=datetime(2026, 7, 10, 12, 0, 0),
        trend_state="insufficient_history",
    )


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

    def test_mode_active_writes_a_pending_suggestion(self, db):
        """Phase 4 supersedes the earlier Phase 1-3 placeholder: 'active'
        mode now writes a real ChurnLabelSuggestion row for a qualifying
        customer (see TestActiveModeWrites for the full denial matrix)."""
        _org_config(db, org_id=1, mode="active")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "evaluated"
        assert result["qualifying"] == 1
        assert result["written"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 1

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
        # Dilute the qualifying share well below the M3b 25% outage-guard
        # threshold (Phase 3) so this Phase 2 test only exercises the
        # batching property, not the guard — 50 / 250 = 20%.
        for i in range(200):
            _trend_eligible_non_qualifying_customer(db, org_id=1, email=f"stable{i}@example.com")

        with _QueryCounter("customer_usage_history") as history_counter:
            result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "shadow"
        assert result["would_suggest"] == 50
        # A small constant, not one-per-customer: 250 customers must not
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


# ===========================================================================
# Phase 3 — M3b population-level outage guard (BEFORE any write path exists)
# ===========================================================================


class TestOutageGuard:
    def test_above_threshold_share_with_sufficient_population_is_suppressed(self, db, caplog):
        _org_config(db, org_id=1, mode="active")
        # 24 trend-eligible customers (population >= min_population=20).
        # 7 of them qualify -> 7/24 = 29.2% > 25% -> suppressed.
        for i in range(7):
            _qualifying_customer(db, org_id=1, email=f"decliner{i}@example.com")
        for i in range(17):
            _trend_eligible_non_qualifying_customer(db, org_id=1, email=f"stable{i}@example.com")

        with caplog.at_level(logging.WARNING):
            result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "suppressed"
        assert result["reason"] == "outage_suspected"
        assert result["qualifying"] == 7
        assert result["eligible"] == 24
        assert db.query(ChurnLabelSuggestion).count() == 0

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, "expected a WARNING log for the outage suppression"
        message = warning_records[0].getMessage()
        assert "7" in message
        assert "24" in message

    def test_same_share_in_tiny_org_is_not_suppressed(self, db):
        _org_config(db, org_id=1, mode="active")
        # 2 of 6 qualify (33%, same ballpark share as above) but population
        # (6) < min_population (20) -> NOT suppressed.
        for i in range(2):
            _qualifying_customer(db, org_id=1, email=f"decliner{i}@example.com")
        for i in range(4):
            _trend_eligible_non_qualifying_customer(db, org_id=1, email=f"stable{i}@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "evaluated"
        assert result["qualifying"] == 2
        assert result["eligible"] == 6

    def test_exactly_at_threshold_is_not_suppressed(self, db):
        _org_config(db, org_id=1, mode="active")
        # 5 of 20 qualify -> exactly 25% -> strict `>` means NOT suppressed.
        for i in range(5):
            _qualifying_customer(db, org_id=1, email=f"decliner{i}@example.com")
        for i in range(15):
            _trend_eligible_non_qualifying_customer(db, org_id=1, email=f"stable{i}@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "evaluated"
        assert result["qualifying"] == 5
        assert result["eligible"] == 20

    def test_not_trend_eligible_customers_excluded_from_population(self, db):
        """insufficient_history customers must not inflate (or deflate) the
        M3b denominator at all."""
        _org_config(db, org_id=1, mode="active")
        for i in range(7):
            _qualifying_customer(db, org_id=1, email=f"decliner{i}@example.com")
        for i in range(17):
            _trend_eligible_non_qualifying_customer(db, org_id=1, email=f"stable{i}@example.com")
        # These must not appear in `eligible` at all — if they did, the
        # share above would dilute below the suppression threshold.
        for i in range(100):
            _not_trend_eligible_customer(db, org_id=1, email=f"newcust{i}@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "suppressed"
        assert result["eligible"] == 24

    def test_shadow_mode_also_honors_outage_guard(self, db):
        _org_config(db, org_id=1, mode="shadow")
        for i in range(7):
            _qualifying_customer(db, org_id=1, email=f"decliner{i}@example.com")
        for i in range(17):
            _trend_eligible_non_qualifying_customer(db, org_id=1, email=f"stable{i}@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "suppressed"
        assert db.query(ChurnLabelSuggestion).count() == 0


# ===========================================================================
# Phase 4 — suggestion write + denials
# ===========================================================================


class TestActiveModeWrites:
    """Denial rule 1: a qualifying 7-day sharp_decline streak in 'active'
    mode writes exactly one ChurnLabelSuggestion row with the expected
    provider, natural key, and suggested_churned_at."""

    def test_qualifying_streak_writes_exactly_one_suggestion(self, db):
        _org_config(db, org_id=1, mode="active")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "evaluated"
        assert result["written"] == 1
        rows = db.query(ChurnLabelSuggestion).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.customer_email == "alice@example.com"
        assert row.provider == "usage_decline"
        expected_streak_start = TODAY - timedelta(days=6)  # 7-day streak, inclusive of TODAY
        assert row.external_opportunity_id == suggestion_key(
            "alice@example.com", expected_streak_start
        )
        assert row.suggested_churned_at == datetime(2026, 7, 10, 12, 0, 0)
        assert row.status == "pending"
        assert row.evidence is not None
        assert row.evidence["streak_start_date"] == expected_streak_start.isoformat()

    def test_running_detector_twice_on_unchanged_streak_still_one_row(self, db):
        """Denial rule 2 — the single most important test in this aspect:
        idempotent via the natural key, across two full detector runs on
        the same session (no commit required between runs — matches
        test_second_run_inserts_zero_rows_unchanged's precedent of relying
        on the flush(), not a full commit, to make the first run's row
        visible to the second run's pre-check)."""
        _org_config(db, org_id=1, mode="active")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        first = detect_usage_decline_labels(1, db, today=TODAY)
        second = detect_usage_decline_labels(1, db, today=TODAY)

        assert first["written"] == 1
        assert second["written"] == 0
        assert second["skipped_existing"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 1

    def test_null_last_active_at_denies_suggestion(self, db):
        """Denial rule 3 — never substitute a fallback date."""
        _org_config(db, org_id=1, mode="active")
        _customer_usage(
            db, 1, "alice@example.com",
            last_active_at=None,
            trend_state=QUALIFYING_STATE,
        )
        _history_rows(db, 1, "alice@example.com", end_date=TODAY, num_days=7)

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["written"] == 0
        assert result["skipped_no_last_active"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_active_churn_event_denies_suggestion(self, db):
        """Denial rule 4."""
        _org_config(db, org_id=1, mode="active")
        _qualifying_customer(db, org_id=1, email="alice@example.com")
        db.add(CustomerChurnEvent(
            organization_id=1,
            customer_email="alice@example.com",
            churned_at=datetime(2026, 1, 1),
            reason_code="other",
            source="manual",
            recovered_at=None,
        ))
        db.commit()

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["written"] == 0
        assert result["skipped_existing"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_recovered_churn_event_customer_is_not_denied(self, db):
        """Companion to rule 4: a RECOVERED churn event must not suppress
        a fresh usage-decline suggestion (mirrors
        test_recovered_churn_event_customer_is_not_skipped in the CRM
        harvester's test suite)."""
        _org_config(db, org_id=1, mode="active")
        _qualifying_customer(db, org_id=1, email="alice@example.com")
        db.add(CustomerChurnEvent(
            organization_id=1,
            customer_email="alice@example.com",
            churned_at=datetime(2026, 1, 1),
            reason_code="other",
            source="manual",
            recovered_at=datetime(2026, 2, 1),
        ))
        db.commit()

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["written"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 1

    def test_cross_org_isolation(self, db):
        """Denial rule 5 — org A's history never yields a suggestion for
        org B."""
        _org_config(db, org_id=1, mode="active")
        _org_config(db, org_id=2, mode="active")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        result_org2 = detect_usage_decline_labels(2, db, today=TODAY)

        assert result_org2["written"] == 0
        assert db.query(ChurnLabelSuggestion).filter_by(organization_id=2).count() == 0
        assert db.query(ChurnLabelSuggestion).count() == 0

        result_org1 = detect_usage_decline_labels(1, db, today=TODAY)

        assert result_org1["written"] == 1
        assert db.query(ChurnLabelSuggestion).filter_by(organization_id=1).count() == 1
        assert db.query(ChurnLabelSuggestion).filter_by(organization_id=2).count() == 0

    def test_per_run_cap_drops_remainder_and_logs(self, db, caplog):
        """Denial rule 6 (house rule: no silent caps). Population is diluted
        well below the M3b 25% outage-guard threshold (same trick as
        TestBatchedHistoryLoad's dilution test) so this test exercises ONLY
        the cap, not the outage guard."""
        _org_config(db, org_id=1, mode="active")
        n_qualifying = PER_RUN_SUGGESTION_CAP + 5
        for i in range(n_qualifying):
            _qualifying_customer(db, org_id=1, email=f"decliner{i}@example.com")
        for i in range(200):
            _trend_eligible_non_qualifying_customer(db, org_id=1, email=f"stable{i}@example.com")

        with caplog.at_level(logging.WARNING):
            result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["written"] == PER_RUN_SUGGESTION_CAP
        assert result["dropped_by_cap"] == 5
        assert db.query(ChurnLabelSuggestion).count() == PER_RUN_SUGGESTION_CAP

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, "expected a WARNING log for the per-run cap"
        message = warning_records[0].getMessage()
        assert str(PER_RUN_SUGGESTION_CAP) in message
        assert "5" in message

    def test_shadow_mode_still_writes_zero_rows(self, db):
        """Denial rule 7 — regression of the Phase 1/3 behaviour, explicitly
        under the Phase 4 write path's existence."""
        _org_config(db, org_id=1, mode="shadow")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "shadow"
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_outage_suppressed_org_writes_zero_rows_even_in_active_mode(self, db):
        """Denial rule 8 — regression of Phase 3's outage guard, explicitly
        under the Phase 4 write path's existence."""
        _org_config(db, org_id=1, mode="active")
        for i in range(7):
            _qualifying_customer(db, org_id=1, email=f"decliner{i}@example.com")
        for i in range(17):
            _trend_eligible_non_qualifying_customer(db, org_id=1, email=f"stable{i}@example.com")

        result = detect_usage_decline_labels(1, db, today=TODAY)

        assert result["status"] == "suppressed"
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_detector_never_commits_caller_owns_transaction(self, db):
        """Caller owns the transaction — the detector must not call
        `db.commit()` itself (it uses `db.begin_nested()` for the per-row
        savepoint only, matching the harvester convention). Verified with a
        commit-call spy rather than an actual ROLLBACK assertion — SQLite's
        pysqlite driver has well-known savepoint/rollback interaction quirks
        under SQLAlchemy's default autocommit-off session config that are
        orthogonal to this property."""
        _org_config(db, org_id=1, mode="active")
        _qualifying_customer(db, org_id=1, email="alice@example.com")

        commit_calls = []
        original_commit = db.commit
        db.commit = lambda: commit_calls.append(1)

        try:
            result = detect_usage_decline_labels(1, db, today=TODAY)
        finally:
            db.commit = original_commit

        assert result["written"] == 1
        assert commit_calls == [], "detect_usage_decline_labels must never call db.commit()"

        db.commit()
        assert db.query(ChurnLabelSuggestion).count() == 1
