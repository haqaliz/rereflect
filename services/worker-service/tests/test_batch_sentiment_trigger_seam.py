"""
batch-sentiment-trigger / trigger-core, Track B — seam-capture tests for
`src.tasks.analysis.analyze_single_feedback` genuinely invoking the
`batch_sentiment_threshold` evaluator.

Strict TDD: written FIRST (RED) before B1-B3's production changes were
wired to prove out, mirroring `tests/test_usage_trend_trigger_seam.py`.

Why this file exists (read before touching)
---------------------------------------------
This repo has shipped a "trigger silently never fires" bug THREE times:
(1) `AutomationEngine` imported inside a bare `except Exception` in
`analysis.py`, swallowing an `ImportError` so `feedback_category_match` /
`sentiment_pattern` never fired in any deployment
(`test_analysis_does_not_swallow_import_error` in
`test_automation_feedback_trigger.py` guards that class specifically); (2)
the backend engine's dead-import equivalent; (3) usage-trend firing that
could regress to in-loop (pre-commit) evaluation
(`test_usage_trend_trigger_seam.py`).

Unit tests in `test_automation_feedback_trigger.py` call
`evaluate_feedback_triggers(...)` directly — they prove the evaluator's
*internal* logic is correct, but they do NOT prove the production call site
(`analysis.py:201`, inside `analyze_single_feedback`) actually reaches it
for this new trigger type. A registration miss (forgetting to add
`batch_sentiment_threshold` to `FEEDBACK_TRIGGER_TYPES`, or forgetting the
`_check_trigger` dispatch `elif`) would leave the rule query silently
filtering the rule out — no exception, no log noise, it just never fires —
exactly the bug class these tests exist to catch.

Self-contained SQLite engine + fixtures, same pattern as
`test_usage_trend_trigger_seam.py` (each wiring/seam test file in this repo
owns its own engine rather than sharing the module-level conftest one).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, FeedbackItem
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


@contextmanager
def _fake_db_session():
    """A `get_db_session`-shaped context manager backed by the same
    StaticPool connection as the `db` fixture, so writes made inside the
    task under test are visible to assertions made through `db` afterward."""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class _CommitTracker:
    def __init__(self):
        self.committed = False


def _make_tracking_db_session(tracker: "_CommitTracker"):
    """Same shape as `_fake_db_session`, but flips `tracker.committed` on the
    FIRST real `session.commit()` call, so a side_effect on the evaluator
    mock can assert it was invoked strictly after that commit landed."""

    @contextmanager
    def _fake():
        session = _SessionLocal()
        original_commit = session.commit

        def _tracked_commit():
            original_commit()
            tracker.committed = True

        session.commit = _tracked_commit
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _fake


def _make_feedback(db: Session, org_id: int = 1, text: str = "feedback text") -> FeedbackItem:
    fb = FeedbackItem(organization_id=org_id, text=text, source="manual")
    fb.sentiment_label = None
    fb.sentiment_score = None
    fb.is_urgent = False
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _seed_analyzed_feedback(db: Session, org_id: int, sentiments, created_at=None):
    for s in sentiments:
        fb = FeedbackItem(
            organization_id=org_id,
            text="seed",
            source="manual",
            sentiment_label=s,
            is_urgent=False,
            created_at=created_at or datetime.utcnow(),
        )
        db.add(fb)
    db.commit()


def _make_batch_rule(db: Session, org_id: int = 1, mode: str = "active", **config_overrides) -> AutomationRule:
    config = {
        "sentiment": "negative",
        "window_hours": 24,
        "mode": "percentage",
        "threshold": 0.5,
        "min_total": 5,
    }
    config.update(config_overrides)
    rule = AutomationRule(
        organization_id=org_id,
        name="Batch sentiment (seam test)",
        trigger_type="batch_sentiment_threshold",
        trigger_config=config,
        actions=[],
        cooldown_hours=24,
        mode=mode,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _fake_analyze_sets_negative(feedback, db=None):
    """Stand-in for the real classifier: deterministically labels the item
    negative without touching VADER/transformers, so these tests are about
    the trigger wiring, not sentiment analysis correctness."""
    feedback.sentiment_label = "negative"
    feedback.sentiment_score = -0.9
    feedback.is_urgent = False


def _reload_analysis():
    import importlib
    import src.tasks.analysis as analysis

    return importlib.reload(analysis)


def _neutralize_side_effects(patches: list):
    """Neutralize the two auto_assign / webhook side effects that
    `analyze_single_feedback` fires after analysis, so the seam tests below
    exercise only the automation-trigger call site."""
    import src.tasks.workflow as workflow_module

    patches.append(patch.object(workflow_module.auto_assign_feedback_batch, "delay", MagicMock()))


# ---------------------------------------------------------------------------
# The central claim (PRD R7 / spec B5): analysis.py's real call site
# genuinely invokes the evaluator for batch_sentiment_threshold, end to end,
# with NOTHING about the evaluator itself mocked.
# ---------------------------------------------------------------------------


class TestEndToEndFiringThroughTheRealSeam:
    def test_batch_sentiment_rule_fires_through_analyze_single_feedback(self, db):
        """A registration miss (FEEDBACK_TRIGGER_TYPES or the `_check_trigger`
        dispatch elif) would make this assert 0 executions with NO exception
        and NO log noise — exactly the silent-never-fire bug class. This is
        deliberately the strongest form of seam test: the real
        `evaluate_feedback_triggers` runs, unmocked."""
        analysis = _reload_analysis()

        org_id = 1
        _seed_analyzed_feedback(db, org_id, ["negative"] * 4 + ["positive"] * 0)
        # 4 pre-existing negative + the pivot item below = 5 total, 5
        # negative -> 100% >= 0.5 threshold, total(5) >= min_total(5).
        rule = _make_batch_rule(db, org_id=org_id, threshold=0.5, min_total=5)
        pivot = _make_feedback(db, org_id=org_id)

        patches = [
            patch.object(analysis, "get_db_session", _fake_db_session),
            patch.object(analysis, "_analyze_feedback_item", _fake_analyze_sets_negative),
            patch.object(
                analysis, "_invalidate_org_cache", MagicMock()
            ),
        ]
        _neutralize_side_effects(patches)

        for p in patches:
            p.start()
        try:
            result = analysis.analyze_single_feedback(pivot.id)
        finally:
            for p in patches:
                p.stop()

        assert result["status"] == "success"

        logs = db.query(AutomationExecution).filter_by(rule_id=rule.id).all()
        assert len(logs) == 1, (
            "expected analyze_single_feedback -> evaluate_feedback_triggers -> "
            "_check_trigger -> _trigger_batch_sentiment to fire and log an "
            "AutomationExecution; got none — the registration/dispatch wiring "
            "for batch_sentiment_threshold is broken"
        )
        assert logs[0].status == "success"
        assert logs[0].organization_id == org_id
        # B3 — org-wide: customer_email must be NULL on the execution row
        # even though this feedback item has none set (belt-and-braces: the
        # column must never carry the "__org__" cooldown sentinel either).
        assert logs[0].customer_email is None

    def test_batch_sentiment_rule_below_min_total_does_not_fire_through_real_seam(self, db):
        """Negative control through the SAME real seam: a window under the
        sample floor must create zero executions, proving the wiring
        doesn't false-fire just because a rule of this type exists."""
        analysis = _reload_analysis()

        org_id = 2
        _seed_analyzed_feedback(db, org_id, ["negative"])  # only 1 pre-existing
        _make_batch_rule(db, org_id=org_id, threshold=0.5, min_total=5)
        pivot = _make_feedback(db, org_id=org_id)

        patches = [
            patch.object(analysis, "get_db_session", _fake_db_session),
            patch.object(analysis, "_analyze_feedback_item", _fake_analyze_sets_negative),
            patch.object(analysis, "_invalidate_org_cache", MagicMock()),
        ]
        _neutralize_side_effects(patches)

        for p in patches:
            p.start()
        try:
            result = analysis.analyze_single_feedback(pivot.id)
        finally:
            for p in patches:
                p.stop()

        assert result["status"] == "success"
        assert db.query(AutomationExecution).filter_by(organization_id=org_id).count() == 0


# ---------------------------------------------------------------------------
# Ordering: the evaluator must be invoked strictly after the pivot item's
# sentiment_label is committed — mirrors test_usage_trend_trigger_seam.py's
# AC4. If analysis.py ever moved the trigger evaluation ahead of the
# analysis commit, the pivot item's own sentiment wouldn't be visible yet.
# ---------------------------------------------------------------------------


class TestOrderingRequirement:
    def test_evaluate_feedback_triggers_called_strictly_after_commit(self, db):
        analysis = _reload_analysis()

        org_id = 3
        _seed_analyzed_feedback(db, org_id, ["negative"] * 4)
        _make_batch_rule(db, org_id=org_id, threshold=0.5, min_total=5)
        pivot = _make_feedback(db, org_id=org_id)

        tracker = _CommitTracker()
        tracking_session_factory = _make_tracking_db_session(tracker)

        mock_evaluate = MagicMock(return_value=[])

        def _assert_committed(*args, **kwargs):
            assert tracker.committed, (
                "evaluate_feedback_triggers was called BEFORE the pivot "
                "feedback item's sentiment_label was committed"
            )
            return []

        mock_evaluate.side_effect = _assert_committed

        patches = [
            patch.object(analysis, "get_db_session", tracking_session_factory),
            patch.object(analysis, "_analyze_feedback_item", _fake_analyze_sets_negative),
            patch.object(analysis, "_invalidate_org_cache", MagicMock()),
            patch.object(analysis, "evaluate_feedback_triggers", mock_evaluate),
        ]
        _neutralize_side_effects(patches)

        for p in patches:
            p.start()
        try:
            analysis.analyze_single_feedback(pivot.id)
        finally:
            for p in patches:
                p.stop()

        mock_evaluate.assert_called_once()
        call_args = mock_evaluate.call_args[0]
        assert call_args[1] == org_id
        assert call_args[2]["feedback_id"] == pivot.id


# ---------------------------------------------------------------------------
# Exception isolation: a raising evaluator must not blow up analysis
# (analysis.py already wraps the call in try/except — this pins that the
# wrapper still covers the new trigger type's failure modes).
# ---------------------------------------------------------------------------


class TestExceptionIsolationAtSeam:
    def test_evaluator_exception_does_not_break_analysis(self, db):
        analysis = _reload_analysis()

        org_id = 4
        pivot = _make_feedback(db, org_id=org_id)

        patches = [
            patch.object(analysis, "get_db_session", _fake_db_session),
            patch.object(analysis, "_analyze_feedback_item", _fake_analyze_sets_negative),
            patch.object(analysis, "_invalidate_org_cache", MagicMock()),
            patch.object(
                analysis, "evaluate_feedback_triggers", MagicMock(side_effect=RuntimeError("boom"))
            ),
        ]
        _neutralize_side_effects(patches)

        for p in patches:
            p.start()
        try:
            result = analysis.analyze_single_feedback(pivot.id)  # must not raise
        finally:
            for p in patches:
                p.stop()

        assert result["status"] == "success"
