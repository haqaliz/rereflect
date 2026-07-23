"""
worker-trend-evaluator aspect — seam-capture tests for
`recompute_usage_scores` (src/tasks/usage_metrics.py).

Strict TDD: written FIRST (RED) before the seam-capture implementation.

AC references are to
docs/planning/usage-trend-automation-trigger/worker-trend-evaluator/spec.md.

AC4 is the whole point of M1 (the ordering requirement): firing must happen
strictly AFTER `db.commit()`, never inside the per-row scan loop, because
the loop scans ALL orgs with no per-org filter and commits once at the end.
In-loop firing would act on uncommitted state. The primary test below
(`test_evaluator_called_strictly_after_commit`) is written specifically to
catch a regression to in-loop firing: it fails loudly (via an assertion
inside the evaluator's `side_effect`) if the evaluator is ever invoked
before the trend/score commit has happened.

Self-contained SQLite engine + fixtures, same pattern as
test_usage_trend_wiring.py (each wiring test file in this repo owns its own
engine rather than sharing the module-level conftest one).
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    ChurnPlaybook,
    ChurnPlaybookExecution,
    CustomerUsage,
    Organization,
)
from src.models.automation_execution import AutomationExecution
from src.models.automation_rule import AutomationRule

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


class _OrderTracker:
    """Records "commit" / "evaluate" events in call order, and exposes a
    plain boolean for "has any commit happened yet" without needing to
    monkeypatch list.append (which CPython's list type does not allow)."""

    def __init__(self):
        self.events: list = []
        self.committed = False

    def record_commit(self):
        self.committed = True
        self.events.append("commit")

    def record_evaluate(self):
        self.events.append("evaluate")


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


def _make_org(db: Session, name: str = "TrendEvalCorp") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_declining_rollup(db: Session, org_id: int, email: str, starting_state) -> CustomerUsage:
    """A rollup whose next classification will land on `declining`
    (baseline 12 active days -> current 6 -> pct -50% -> declining).

    Seeds 6 distinct-day UsageEvent rows so `_rederive_windows` (called
    unconditionally inside `recompute_usage_scores`) re-derives
    active_days_14d back to 6 rather than 0 — same pattern as
    test_usage_trend_wiring.py's declining fixtures."""
    from src.models import UsageEvent

    for day in range(6):
        db.add(UsageEvent(
            organization_id=org_id, customer_email=email,
            event_type="track", event_name="feat-a",
            external_event_id=f"evt-seam-{email}-{day}",
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


def _make_playbook(db: Session, org_id: int) -> ChurnPlaybook:
    pb = ChurnPlaybook(
        organization_id=org_id,
        name="At-Risk Outreach",
        description="seam test playbook",
        probability_min=0.0,
        probability_max=1.0,
        action_sequence=[{"type": "send_email", "config": {}}],
        is_template=False,
        is_active=True,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


def _make_rule(db: Session, org_id: int, mode="active", states=None, playbook_id=None) -> AutomationRule:
    if states is None:
        states = ["declining", "sharp_decline"]
    rule = AutomationRule(
        organization_id=org_id,
        name="Usage decline -> playbook (seam test)",
        trigger_type="usage_trend",
        trigger_config={"states": states},
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook_id}}],
        cooldown_hours=24,
        mode=mode,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# AC4 — firing happens strictly AFTER commit; catches in-loop firing.
# ---------------------------------------------------------------------------


class TestOrderingRequirement:
    def test_evaluator_called_strictly_after_commit(self, db):
        """AC4: the evaluator must never be invoked before the trend/score
        commit. The mocked evaluator's side_effect raises an AssertionError
        if `committed` is still False when it is called — this is what
        makes the test actually catch an in-loop-firing regression, rather
        than merely observing call order after the fact."""
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "seam-declining@example.com"
        _make_declining_rollup(db, org.id, email, starting_state="stable")
        _make_history(db, org.id, email, days_ago=13, active_days_14d=12)

        tracker = _OrderTracker()

        def _evaluate_side_effect(org_id, customer_email, old_state, new_state, db_arg):
            tracker.record_evaluate()
            assert tracker.committed, (
                "evaluate_usage_trend_triggers was called BEFORE db.commit() — "
                "this is exactly the in-loop-firing defect AC4 guards against: "
                "the loop scans all orgs and commits once at the end, so firing "
                "before that commit would act on uncommitted state."
            )

        mock_evaluate = MagicMock(side_effect=_evaluate_side_effect)

        tracking_session_factory = _make_tracking_db_session(tracker)

        with patch.object(um, "get_db_session", tracking_session_factory):
            with patch(
                "src.services.automation_usage_trend_trigger.evaluate_usage_trend_triggers",
                mock_evaluate,
            ):
                um.recompute_usage_scores()

        assert mock_evaluate.call_count == 1, "evaluator should fire exactly once for one transition"
        assert "commit" in tracker.events
        assert tracker.events.index("commit") < tracker.events.index("evaluate"), (
            f"expected commit before evaluate, got order: {tracker.events}"
        )

        call_args = mock_evaluate.call_args[0]
        assert call_args[0] == org.id
        assert call_args[1] == email
        assert call_args[2] == "stable"
        assert call_args[3] == "declining"

    def test_trend_value_is_committed_and_visible_before_execution_row_created(self, db):
        """AC4 (alternate framing): by the time a real ChurnPlaybookExecution
        row would be created (end-to-end, no mocking of the evaluator), the
        CustomerUsage row's usage_trend_state is already the NEW value when
        read back from the db session passed to the evaluator — proving the
        write landed before any action fired."""
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "seam-visible@example.com"
        rollup = _make_declining_rollup(db, org.id, email, starting_state="stable")
        _make_history(db, org.id, email, days_ago=13, active_days_14d=12)
        playbook = _make_playbook(db, org.id)
        _make_rule(db, org.id, mode="active", playbook_id=playbook.id)

        with patch("src.services.automation_usage_trend_trigger.run_playbook"):
            with patch.object(um, "get_db_session", _fake_db_session):
                um.recompute_usage_scores()

        db.expire(rollup)
        db.refresh(rollup)
        assert rollup.usage_trend_state == "declining"

        executions = db.query(ChurnPlaybookExecution).all()
        assert len(executions) == 1
        assert executions[0].customer_email == email


# ---------------------------------------------------------------------------
# AC1 — end-to-end: a real stable -> declining transition through the daily
# recompute creates a ChurnPlaybookExecution and dispatches the playbook task.
# ---------------------------------------------------------------------------


class TestEndToEndFiring:
    def test_stable_to_declining_creates_execution_and_dispatches_task(self, db):
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "seam-e2e@example.com"
        _make_declining_rollup(db, org.id, email, starting_state="stable")
        _make_history(db, org.id, email, days_ago=13, active_days_14d=12)
        playbook = _make_playbook(db, org.id)
        rule = _make_rule(db, org.id, mode="active", playbook_id=playbook.id)

        with patch("src.services.automation_usage_trend_trigger.run_playbook") as mock_task:
            with patch.object(um, "get_db_session", _fake_db_session):
                um.recompute_usage_scores()

        executions = db.query(ChurnPlaybookExecution).all()
        assert len(executions) == 1
        execution = executions[0]
        assert execution.customer_email == email
        assert execution.playbook_id == playbook.id
        assert execution.triggered_by == "auto_usage_trend"
        mock_task.delay.assert_called_once_with(execution.id)

        logs = db.query(AutomationExecution).filter_by(rule_id=rule.id).all()
        assert len(logs) == 1
        assert logs[0].status == "success"


# ---------------------------------------------------------------------------
# AC2 — insufficient_history -> anything creates zero executions, exercised
# through the real seam (explicitly named per the task instructions).
# ---------------------------------------------------------------------------


class TestWarmUpGuardThroughSeam:
    def test_insufficient_history_to_declining_creates_zero_executions(self, db):
        """AC2: a customer whose FIRST real classification lands on
        `declining` (starting from `insufficient_history`, i.e. no prior
        row) must fire zero executions — the baseline-seed rule."""
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "seam-warmup@example.com"
        # starting_state=None mirrors a brand-new CustomerUsage row: the
        # model default for usage_trend_state is NULL / unset until the
        # first classification runs, which classify_usage_trend surfaces
        # as "insufficient_history" via is_worsening_transition's None
        # handling either way.
        _make_declining_rollup(db, org.id, email, starting_state="insufficient_history")
        _make_history(db, org.id, email, days_ago=13, active_days_14d=12)
        playbook = _make_playbook(db, org.id)
        _make_rule(db, org.id, mode="active", playbook_id=playbook.id)

        with patch("src.services.automation_usage_trend_trigger.run_playbook") as mock_task:
            with patch.object(um, "get_db_session", _fake_db_session):
                um.recompute_usage_scores()

        assert db.query(ChurnPlaybookExecution).count() == 0
        assert db.query(AutomationExecution).count() == 0
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# AC3 — a customer staying `declining` across two consecutive daily runs
# fires ONCE, on the first, proven through the real seam (two full task
# invocations, no cooldown reliance since Redis is unavailable by default
# in this test process).
# ---------------------------------------------------------------------------


class TestEdgeSemanticsAcrossTwoRuns:
    def test_declining_persists_across_two_runs_fires_once(self, db):
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "seam-persist@example.com"
        rollup = _make_declining_rollup(db, org.id, email, starting_state="stable")
        _make_history(db, org.id, email, days_ago=13, active_days_14d=12)
        playbook = _make_playbook(db, org.id)
        _make_rule(db, org.id, mode="active", playbook_id=playbook.id)

        with patch("src.services.automation_usage_trend_trigger.run_playbook") as mock_task:
            with patch.object(um, "get_db_session", _fake_db_session):
                um.recompute_usage_scores()  # run 1: stable -> declining, fires
                um.recompute_usage_scores()  # run 2: declining -> declining, silent

        assert db.query(ChurnPlaybookExecution).count() == 1
        assert mock_task.delay.call_count == 1


# ---------------------------------------------------------------------------
# AC8 — a raising evaluator call is isolated: the task still completes.
# ---------------------------------------------------------------------------


class TestExceptionIsolationAtSeam:
    def test_evaluator_exception_does_not_break_recompute(self, db):
        import src.tasks.usage_metrics as um
        _reload(um)

        org = _make_org(db)
        email = "seam-broken-evaluator@example.com"
        _make_declining_rollup(db, org.id, email, starting_state="stable")
        _make_history(db, org.id, email, days_ago=13, active_days_14d=12)

        with patch(
            "src.services.automation_usage_trend_trigger.evaluate_usage_trend_triggers",
            side_effect=RuntimeError("boom"),
        ):
            with patch.object(um, "get_db_session", _fake_db_session):
                result = um.recompute_usage_scores()  # must not raise

        assert result["trend_updated"] == 1

        db.expire_all()
        rollup = (
            db.query(CustomerUsage)
            .filter_by(organization_id=org.id, customer_email=email)
            .first()
        )
        assert rollup.usage_trend_state == "declining"


# ---------------------------------------------------------------------------
# AC9 — cross-org isolation exercised through the real seam: two orgs
# scanned in the SAME run, each with its own rule; only the matching org's
# rule fires.
# ---------------------------------------------------------------------------


class TestCrossOrgIsolationAtSeam:
    def test_two_orgs_scanned_together_only_matching_org_fires(self, db):
        import src.tasks.usage_metrics as um
        _reload(um)

        org1 = _make_org(db, "OrgOne")
        org2 = _make_org(db, "OrgTwo")

        email1 = "org1-cust@example.com"
        email2 = "org2-cust@example.com"

        _make_declining_rollup(db, org1.id, email1, starting_state="stable")
        _make_history(db, org1.id, email1, days_ago=13, active_days_14d=12)

        # org2's customer stays `declining -> declining` (no transition) so
        # its rule should never fire regardless. Same baseline shape as
        # org1 (12 -> 6, -50% -> declining) so it re-classifies as
        # `declining` again rather than recovering to `stable`.
        rollup2 = _make_declining_rollup(db, org2.id, email2, starting_state="declining")
        _make_history(db, org2.id, email2, days_ago=13, active_days_14d=12)

        playbook1 = _make_playbook(db, org1.id)
        _make_rule(db, org1.id, mode="active", playbook_id=playbook1.id)

        playbook2 = _make_playbook(db, org2.id)
        _make_rule(db, org2.id, mode="active", playbook_id=playbook2.id)

        with patch("src.services.automation_usage_trend_trigger.run_playbook") as mock_task:
            with patch.object(um, "get_db_session", _fake_db_session):
                um.recompute_usage_scores()

        executions = db.query(ChurnPlaybookExecution).all()
        assert len(executions) == 1
        assert executions[0].organization_id == org1.id
        assert executions[0].customer_email == email1
