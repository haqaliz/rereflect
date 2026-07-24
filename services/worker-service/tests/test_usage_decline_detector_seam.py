"""
worker-detector aspect — Phase 5 seam-capture tests for
`recompute_usage_scores` (src/tasks/usage_metrics.py).

Strict TDD: written FIRST (RED) before the wiring.

CRITICAL PLACEMENT (plan section 1 / spec correction): the detector must
run STRICTLY AFTER the daily snapshot commit (`usage_metrics.py:693-694`),
never at the M3.2c post-commit drain seam (`:667-681`). Today's snapshot
row does not exist until that final commit, so a detector run before it
would read history missing the current day.

Modeled directly on `test_usage_trend_trigger_seam.py`'s in-`side_effect`
assertion technique (that file, not backend-api, is the closest precedent
in this repo — same self-contained-engine convention). Each wiring test
file in this repo owns its own SQLite engine rather than sharing the
module-level conftest one.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, CustomerUsage, Organization

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
# Order/commit tracker (mirrors test_usage_trend_trigger_seam.py:67-107)
# ---------------------------------------------------------------------------


class _OrderTracker:
    """Records "commit" / "detect" events in call order, and a running
    commit count so the ordering test below can assert on a PRECISE commit
    count at the moment the detector fires — not just "any commit has
    happened" — which is what actually distinguishes the correct placement
    (after BOTH the score/trend commit AND the snapshot commit) from the
    M3.2c drain seam (after only the FIRST of those two commits)."""

    def __init__(self):
        self.events: list = []
        self.commit_count = 0

    def record_commit(self):
        self.commit_count += 1
        self.events.append("commit")

    def record_detect(self):
        self.events.append("detect")


def _make_tracking_db_session(tracker: "_OrderTracker"):
    """A `get_db_session`-shaped context manager whose `commit()` is spied
    on, recording a "commit" event on every real commit call."""

    @contextmanager
    def _fake_db_session():
        session = _SessionLocal()
        original_commit = session.commit

        def _tracked_commit():
            original_commit()
            tracker.record_commit()

        session.commit = _tracked_commit
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _fake_db_session


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


def _reload(um):
    import importlib
    importlib.reload(um)
    return um


def _make_org(db: Session, name: str = "SeamCorp") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_declining_rollup(db: Session, org_id: int, email: str, starting_state) -> CustomerUsage:
    """A rollup whose next classification will land on `declining`
    (baseline 12 active days -> current 6 -> pct -50% -> declining) — same
    shape as test_usage_trend_trigger_seam.py's fixture of the same name,
    used here purely to GUARANTEE the score/trend commit branch executes
    (so the ordering test below has two distinct, countable commits: the
    score/trend commit, then the always-unconditional snapshot commit)."""
    from src.models import UsageEvent

    for day in range(6):
        db.add(UsageEvent(
            organization_id=org_id, customer_email=email,
            event_type="track", event_name="feat-a",
            external_event_id=f"evt-decline-seam-{email}-{day}",
            occurred_at=datetime.utcnow() - timedelta(days=day),
            received_at=datetime.utcnow(),
        ))
    db.commit()

    rollup = CustomerUsage(
        organization_id=org_id,
        customer_email=email,
        last_active_at=datetime.utcnow(),
        usage_score=50,
        active_days_7d=6,
        active_days_14d=6,
        active_days_30d=6,
        usage_trend_state=starting_state,
    )
    db.add(rollup)
    db.commit()
    db.refresh(rollup)
    return rollup


def _make_history(db: Session, org_id: int, email: str, days_ago: int, active_days_14d: int):
    from src.models import CustomerUsageHistory

    row = CustomerUsageHistory(
        organization_id=org_id,
        customer_email=email,
        snapshot_date=datetime.utcnow().date() - timedelta(days=days_ago),
        active_days_14d=active_days_14d,
    )
    db.add(row)
    db.commit()
    return row


def _make_plain_customer_usage(db: Session, org_id: int, email: str) -> CustomerUsage:
    """A minimal rollup with no UsageEvent rows — score/windows/trend all
    stay stable between runs (nothing to change), so this fixture is only
    used where the test just needs *some* customer_usage row for its org to
    appear in `rows`/the snapshot batch, without caring about score/trend
    transitions."""
    row = CustomerUsage(
        organization_id=org_id,
        customer_email=email,
        last_active_at=datetime.utcnow(),
        usage_score=50,
        usage_trend_state="stable",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Test 1 — ordering: detector invoked strictly AFTER the snapshot commit.
# ---------------------------------------------------------------------------


class TestOrderingRequirement:
    def test_detector_called_strictly_after_snapshot_commit(self, db):
        """Regression guard for the plan's placement correction: if the
        detector were (wrongly) invoked at the M3.2c drain seam, it would
        fire after exactly ONE commit (the score/trend commit) — BEFORE the
        always-unconditional snapshot commit. The side_effect below asserts
        the commit count is exactly 2 (score/trend commit + snapshot
        commit) at the moment the detector is called, which fails loudly
        under that regression."""
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "seam-order@example.com"
        _make_declining_rollup(db, org.id, email, starting_state="stable")
        _make_history(db, org.id, email, days_ago=13, active_days_14d=12)

        tracker = _OrderTracker()

        def _detect_side_effect(org_id, db_arg, **kwargs):
            tracker.record_detect()
            assert tracker.commit_count == 2, (
                f"detect_usage_decline_labels called after {tracker.commit_count} "
                "commit(s), expected exactly 2 (score/trend commit, then the "
                "snapshot commit) — this is exactly the wrong-placement defect "
                "the plan's section 1 correction guards against: placing the "
                "detector at the M3.2c drain seam would fire it after only the "
                "FIRST commit, before today's snapshot row exists."
            )
            return {"status": "skipped", "reason": "mode_off"}

        mock_detect = MagicMock(side_effect=_detect_side_effect)
        tracking_session_factory = _make_tracking_db_session(tracker)

        with patch.object(um, "get_db_session", tracking_session_factory):
            with patch(
                "src.services.usage_decline_label_detector.detect_usage_decline_labels",
                mock_detect,
            ):
                um.recompute_usage_scores()

        assert mock_detect.call_count == 1
        assert "detect" in tracker.events
        # At least the score/trend commit AND the snapshot commit precede
        # the detect call (the side_effect above already asserted the
        # PRECISE count — commit_count == 2 — at the exact moment of the
        # call; this is a looser, post-hoc corroboration that at least two
        # commits happened somewhere before "detect" in the event order).
        detect_index = tracker.events.index("detect")
        commits_before_detect = tracker.events[:detect_index].count("commit")
        assert commits_before_detect == 2, (
            f"expected exactly 2 commits before the detect call, got "
            f"{commits_before_detect} (full event order: {tracker.events})"
        )

        call_args = mock_detect.call_args
        assert call_args[0][0] == org.id


# ---------------------------------------------------------------------------
# Test 2 — isolation: one org's detector exception must not break the task
# or prevent other orgs from being processed.
# ---------------------------------------------------------------------------


class TestExceptionIsolationAcrossOrgs:
    def test_one_org_raising_does_not_prevent_others_or_fail_task(self, db, caplog):
        import src.tasks.usage_metrics as um
        _reload(um)

        org_broken = _make_org(db, "BrokenOrg")
        org_ok = _make_org(db, "OkOrg")

        _make_plain_customer_usage(db, org_broken.id, "broken-cust@example.com")
        _make_plain_customer_usage(db, org_ok.id, "ok-cust@example.com")

        called_org_ids: list = []

        def _detect_side_effect(org_id, db_arg, **kwargs):
            called_org_ids.append(org_id)
            if org_id == org_broken.id:
                raise RuntimeError("boom: usage_decline_label_detector blew up")
            return {"status": "skipped", "reason": "mode_off"}

        mock_detect = MagicMock(side_effect=_detect_side_effect)

        with caplog.at_level(logging.ERROR):
            with patch.object(um, "get_db_session", _fake_db_session):
                with patch(
                    "src.services.usage_decline_label_detector.detect_usage_decline_labels",
                    mock_detect,
                ):
                    result = um.recompute_usage_scores()  # must not raise

        assert org_broken.id in called_org_ids
        assert org_ok.id in called_org_ids
        assert result["total"] == 2

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "expected an ERROR log for the broken org"
        assert any(str(org_broken.id) in r.getMessage() for r in error_records)


# ---------------------------------------------------------------------------
# Test 3 — snapshot_written == 0 -> detector skipped, and the skip is
# logged.
# ---------------------------------------------------------------------------


class TestSkippedWhenSnapshotWriteFailed:
    def test_snapshot_write_failure_skips_detector_and_logs(self, db, caplog):
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        _make_plain_customer_usage(db, org.id, "seam-skip@example.com")

        mock_detect = MagicMock()

        with caplog.at_level(logging.INFO):
            with patch.object(um, "get_db_session", _fake_db_session):
                with patch.object(
                    um, "_write_usage_history_snapshots",
                    side_effect=RuntimeError("boom: snapshot write failed"),
                ):
                    with patch(
                        "src.services.usage_decline_label_detector.detect_usage_decline_labels",
                        mock_detect,
                    ):
                        result = um.recompute_usage_scores()  # must not raise

        assert result["snapshot_written"] == 0
        mock_detect.assert_not_called()

        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any(
            "usage_decline_label_detector" in r.getMessage() and "skip" in r.getMessage().lower()
            for r in info_records
        ), "expected an INFO log recording that the detector was skipped"
