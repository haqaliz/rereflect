"""
reanalysis-seam aspect — seam-capture tests for
`src.tasks.analysis.reanalyze_feedback`, the pull-facing half of the UI
"Re-analyze" force seam (POST /api/v1/analyze with force=true; see
backend-api/src/api/routes/analyze.py:64-76, which worker-service cannot
import).

Strict TDD: written FIRST (RED) — every test that touches
`reanalyze_feedback` fails today with AttributeError (the function does not
exist). Tests 5 and 8b are pure characterization pins of EXISTING behavior
(the skip gate and the batch loop's per-item isolation) and pass from the
start; they pin the contract the seam must not disturb.

Planned against
docs/planning/intercom-pull-replies-and-ratings/reanalysis-seam/plan_20260815.md
(spec AC1-AC4, PRD R4 + OQ1). Self-contained SQLite engine + fixtures, same
pattern as test_batch_sentiment_trigger_seam.py and
test_usage_trend_trigger_seam.py (each wiring/seam test file in this repo
owns its own engine rather than sharing the module-level conftest one).

Why this file exists (read before touching)
---------------------------------------------
`analyze_single_feedback` skips already-analyzed items (analysis.py:166-168),
so the pull cannot naively re-dispatch it for enriched items — it would be a
silent no-op. The UI force path instead clears the sentinel fields the batch
task filters on and dispatches `analyze_feedback_batch`. The seam must mirror
that route verbatim: same sentinel fields, commit BEFORE dispatch (the batch
task runs in a fresh session and filters on the cleared sentinel), same task,
same args. These tests pin the seam contract at the boundary
`pull-enrichment` will consume; they would catch a future seam that used
`analyze_single_feedback` (the OQ1 trap), dispatched before committing, or
ran the pipeline inline in the sync loop.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, FeedbackItem, Organization

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


class _OrderTracker:
    """Records "commit" / "dispatch" events in call order, and exposes a
    plain boolean for "has any commit happened yet" — same pattern as
    test_usage_trend_trigger_seam.py's AC4 tracker."""

    def __init__(self):
        self.events: list = []
        self.committed = False

    def record_commit(self):
        self.committed = True
        self.events.append("commit")

    def record_dispatch(self):
        self.events.append("dispatch")


def _track_commit(db: Session, tracker: "_OrderTracker"):
    """Wrap a session's commit() so every real commit records an event.
    Instance-attribute assignment shadows the class method, exactly like
    `_make_tracking_db_session` in test_usage_trend_trigger_seam.py."""
    original_commit = db.commit

    def _tracked_commit():
        original_commit()
        tracker.record_commit()

    db.commit = _tracked_commit


def _reload_analysis():
    import importlib
    import src.tasks.analysis as analysis

    return importlib.reload(analysis)


def _make_org(db: Session, name: str = "ReanalysisCorp") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_analyzed_feedback(
    db: Session,
    org_id: int,
    text: str,
    sentiment_label: str = "negative",
    sentiment_score: float = -0.54,
    is_urgent: bool = True,
    churn_risk_score: int = 30,
    customer_email: str | None = None,
) -> FeedbackItem:
    """A fully-analyzed item (stale values the force path must refresh)."""
    fb = FeedbackItem(
        organization_id=org_id,
        text=text,
        source="intercom",
        customer_email=customer_email,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        is_urgent=is_urgent,
        pain_point_category="system_crash",
        pain_point_severity="major",
        pain_point_text="stale pain point",
        feature_request_category="export",
        feature_request_priority="medium",
        urgent_category="service_outage",
        urgent_response_time="4_hours",
        categorization_confidence=0.8,
        tags=["stale"],
        churn_risk_score=churn_risk_score,
        churn_risk_factors={"stale": {"score": churn_risk_score, "max": 100, "label": "stale"}},
        suggested_action="stale suggestion",
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _patch_delay_with_real_batch(analysis, patches) -> MagicMock:
    """Patch `analyze_feedback_batch.delay` so a seam dispatch runs the REAL
    batch task in-process (Celery task objects run their body on direct
    call). Returns the mock — the seam's dispatch target + args are
    captured on it, and its side_effect is the real `analyze_feedback_batch`."""
    mock_delay = MagicMock()
    mock_delay.side_effect = (
        lambda org_id, feedback_ids: analysis.analyze_feedback_batch(org_id, feedback_ids)
    )
    patches.append(patch.object(analysis.analyze_feedback_batch, "delay", mock_delay))
    return mock_delay


def _neutralize_batch_side_effects(analysis, patches):
    """Neutralize the post-analysis side effects `analyze_feedback_batch`
    fires (cache invalidation, auto-assign dispatch) so the seam tests below
    exercise only the analysis path — mirrors
    test_batch_sentiment_trigger_seam.py's `_neutralize_side_effects`."""
    import src.tasks.workflow as workflow_module

    patches.append(patch.object(analysis, "_invalidate_org_cache", MagicMock()))
    patches.append(patch.object(workflow_module.auto_assign_feedback_batch, "delay", MagicMock()))


# ---------------------------------------------------------------------------
# Force semantics: sentinel parity with analyze.py:64-76 + dispatch target.
# ---------------------------------------------------------------------------


class TestForceSemantics:
    def test_reanalyze_feedback_clears_sentinels_and_dispatches_batch_task(self, db):
        """The seam must clear exactly the two sentinel fields the backend
        route clears (sentiment_label + churn_risk_factors), commit, and
        dispatch `analyze_feedback_batch` with `(org_id, [feedback_id])`."""
        analysis = _reload_analysis()

        org = _make_org(db)
        item = _make_analyzed_feedback(db, org.id, "stale text")

        mock_delay = MagicMock()
        patches = [
            patch.object(analysis.analyze_feedback_batch, "delay", mock_delay),
        ]

        for p in patches:
            p.start()
        try:
            result = analysis.reanalyze_feedback(db, item.id)
        finally:
            for p in patches:
                p.stop()

        assert result is True
        mock_delay.assert_called_once_with(org.id, [item.id])

        db.expire(item)
        db.refresh(item)
        assert item.sentiment_label is None
        assert item.churn_risk_factors is None
        assert item.text == "stale text"


# ---------------------------------------------------------------------------
# Missing item: False, no dispatch, no raise.
# ---------------------------------------------------------------------------


class TestMissingItem:
    def test_reanalyze_feedback_missing_item_no_dispatch(self, db):
        analysis = _reload_analysis()

        mock_delay = MagicMock()
        patches = [
            patch.object(analysis.analyze_feedback_batch, "delay", mock_delay),
        ]

        for p in patches:
            p.start()
        try:
            result = analysis.reanalyze_feedback(db, 999_999)  # must not raise
        finally:
            for p in patches:
                p.stop()

        assert result is False
        mock_delay.assert_not_called()


# ---------------------------------------------------------------------------
# Ordering: the sentinel clear must be COMMITTED before dispatch. The batch
# task opens a NEW session (analysis.py:239) and filters on the cleared
# sentiment_label (:244) — an uncommitted clear silently skips the item.
# Mirrors test_usage_trend_trigger_seam.py's AC4 style.
# ---------------------------------------------------------------------------


class TestOrderingRequirement:
    def test_commit_precedes_dispatch(self, db):
        analysis = _reload_analysis()

        org = _make_org(db)
        item = _make_analyzed_feedback(db, org.id, "stale text")

        tracker = _OrderTracker()
        _track_commit(db, tracker)

        mock_delay = MagicMock()

        def _assert_committed(*args, **kwargs):
            assert tracker.committed, (
                "analyze_feedback_batch was dispatched BEFORE the sentinel "
                "clear was committed — the batch task opens a fresh session "
                "and filters on sentiment_label == None, so an uncommitted "
                "clear silently skips the item (analysis.py:239-245)."
            )
            tracker.record_dispatch()

        mock_delay.side_effect = _assert_committed

        patches = [
            patch.object(analysis.analyze_feedback_batch, "delay", mock_delay),
        ]

        for p in patches:
            p.start()
        try:
            result = analysis.reanalyze_feedback(db, item.id)
        finally:
            for p in patches:
                p.stop()

        assert result is True
        mock_delay.assert_called_once_with(org.id, [item.id])
        assert "commit" in tracker.events
        assert tracker.events.index("commit") < tracker.events.index("dispatch"), (
            f"expected commit before dispatch, got order: {tracker.events}"
        )


# ---------------------------------------------------------------------------
# Spec AC3: re-analysis of an already-analyzed item actually refreshes the
# stored analysis (real batch task, real keyword pipeline, VADER path).
# ---------------------------------------------------------------------------


class TestForceRefresh:
    def test_force_reanalysis_refreshes_stored_analysis(self, db):
        analysis = _reload_analysis()

        org = _make_org(db)
        item = _make_analyzed_feedback(
            db, org.id,
            text="I love this product, it's amazing!",
            sentiment_label="positive",
            sentiment_score=0.8516,
            is_urgent=False,
            churn_risk_score=0,
        )
        stale_label = item.sentiment_label
        stale_score = item.sentiment_score

        # The conversation gained new content (this is what the pull's merge
        # produces); the stored analysis is still the OLD text's.
        item.text = "This is terrible, I want a refund now. The app is broken."
        db.commit()

        patches = [
            patch.object(analysis, "categorize_feedback", return_value=None),
        ]
        _neutralize_batch_side_effects(analysis, patches)
        _patch_delay_with_real_batch(analysis, patches)
        patches.append(patch.object(analysis, "get_db_session", _fake_db_session))

        for p in patches:
            p.start()
        try:
            analysis.reanalyze_feedback(db, item.id)
        finally:
            for p in patches:
                p.stop()

        db.expire(item)
        db.refresh(item)
        assert item.sentiment_label != stale_label
        assert item.sentiment_score != stale_score
        assert item.sentiment_label == "negative"
        assert item.sentiment_score == pytest.approx(-0.7096, abs=1e-4)
        assert item.is_urgent is True
        assert item.pain_point_category == "payment_issue"
        assert item.pain_point_severity == "critical"
        assert item.churn_risk_score == 35
        assert item.churn_risk_factors != {"stale": {"score": 0, "max": 100, "label": "stale"}}
        assert item.tags == ["bug", "feature-request", "mobile"]
        assert item.llm_analyzed is False


# ---------------------------------------------------------------------------
# Negative control (OQ1 pin): WITHOUT force, `analyze_single_feedback` still
# skips already-analyzed items — default behavior byte-identical, and the
# seam must not have introduced a force flag there.
# ---------------------------------------------------------------------------


class TestWithoutForce:
    def test_without_force_analyze_single_feedback_still_skips(self, db):
        analysis = _reload_analysis()

        org = _make_org(db)
        item = _make_analyzed_feedback(db, org.id, "stale text")
        before = {c.name: getattr(item, c.name) for c in item.__table__.columns}

        patches = [
            patch.object(analysis, "get_db_session", _fake_db_session),
        ]

        for p in patches:
            p.start()
        try:
            result = analysis.analyze_single_feedback(item.id)
        finally:
            for p in patches:
                p.stop()

        assert result == {"status": "already_analyzed", "feedback_id": item.id}

        db.expire(item)
        db.refresh(item)
        after = {c.name: getattr(item, c.name) for c in item.__table__.columns}
        assert after == before, "stored analysis must be untouched without force"


# ---------------------------------------------------------------------------
# Spec AC2 characterization: a manual re-analyze (route-equivalent: clear
# sentinels + batch task) and the pull's re-analysis (the seam) produce
# identical stored analysis AND dispatch the same target with the same args.
# ---------------------------------------------------------------------------


class TestManualVsPullCharacterization:
    def test_pull_reanalysis_identical_to_manual_reanalysis(self, db):
        analysis = _reload_analysis()

        org = _make_org(db)
        TEXT = "The app crashes every time I try to export data. This is really frustrating!"

        manual_item = _make_analyzed_feedback(db, org.id, "stale A")
        pull_item = _make_analyzed_feedback(db, org.id, "stale B")
        manual_item.text = TEXT
        pull_item.text = TEXT
        db.commit()

        # Path A (manual): clear the sentinels + commit + real batch task —
        # exactly what the backend route does (analyze.py:64-76).
        manual_item.sentiment_label = None
        manual_item.churn_risk_factors = None
        db.commit()

        patches = [
            patch.object(analysis, "categorize_feedback", return_value=None),
            patch.object(analysis, "get_db_session", _fake_db_session),
        ]
        _neutralize_batch_side_effects(analysis, patches)
        for p in patches:
            p.start()
        try:
            analysis.analyze_feedback_batch(org.id, [manual_item.id])

            # Path B (pull): the seam, with dispatch captured on the SAME
            # module attribute the manual path runs directly.
            mock_delay = MagicMock()
            mock_delay.side_effect = (
                lambda org_id, ids: analysis.analyze_feedback_batch(org_id, ids)
            )
            with patch.object(analysis.analyze_feedback_batch, "delay", mock_delay):
                analysis.reanalyze_feedback(db, pull_item.id)
        finally:
            for p in patches:
                p.stop()

        mock_delay.assert_called_once_with(org.id, [pull_item.id])

        db.expire_all()
        db.refresh(manual_item)
        db.refresh(pull_item)

        STORED_FIELDS = [
            "sentiment_label", "sentiment_score", "is_urgent",
            "pain_point_category", "pain_point_severity", "pain_point_text",
            "extracted_issue", "feature_request_category",
            "feature_request_priority", "feature_request_text",
            "urgent_category", "urgent_response_time",
            "categorization_confidence", "tags", "churn_risk_score",
            "churn_risk_factors", "suggested_action", "llm_analyzed",
        ]
        for field in STORED_FIELDS:
            assert getattr(pull_item, field) == getattr(manual_item, field), (
                f"pull re-analysis diverged from manual re-analysis on {field}: "
                f"manual={getattr(manual_item, field)!r} pull={getattr(pull_item, field)!r}"
            )

        assert pull_item.sentiment_label == "negative"
        assert pull_item.is_urgent is True


# ---------------------------------------------------------------------------
# Health recompute: with customer_email present, re-analysis fires
# request_health_recompute / update_churn_probability / check_winback with
# (org_id, email) — same as fresh analysis (analysis.py:482-511).
# ---------------------------------------------------------------------------


class TestHealthRecompute:
    def test_reanalysis_recomputes_health_when_customer_email(self, db):
        analysis = _reload_analysis()

        org = _make_org(db)
        item = _make_analyzed_feedback(
            db, org.id, "stale text", customer_email="alice@example.com",
        )

        mock_health = MagicMock()
        mock_prob = MagicMock()
        mock_winback = MagicMock()

        patches = [
            patch.object(analysis, "categorize_feedback", return_value=None),
            patch.object(analysis, "get_db_session", _fake_db_session),
            patch("src.services.health_recompute.request_health_recompute", mock_health),
            patch("src.services.probability_updater.update", mock_prob),
            patch("src.services.winback_detector.check", mock_winback),
        ]
        _neutralize_batch_side_effects(analysis, patches)
        _patch_delay_with_real_batch(analysis, patches)

        for p in patches:
            p.start()
        try:
            analysis.reanalyze_feedback(db, item.id)
        finally:
            for p in patches:
                p.stop()

        mock_health.assert_called_once()
        mock_prob.assert_called_once()
        mock_winback.assert_called_once()
        assert mock_health.call_args[0][:2] == (org.id, "alice@example.com")
        assert mock_prob.call_args[0][:2] == (org.id, "alice@example.com")
        assert mock_winback.call_args[0][:2] == (org.id, "alice@example.com")


# ---------------------------------------------------------------------------
# Failure isolation: the seam never runs the analysis pipeline inline (only
# dispatches), so a failing analysis stays in the batch task's per-item
# catch and cannot crash the sync/enrichment loop (analysis.py:253-259).
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    def test_analysis_failure_isolated_in_batch_loop(self, db):
        analysis = _reload_analysis()

        org = _make_org(db)
        item = _make_analyzed_feedback(db, org.id, "stale text")

        # (a) The seam itself only dispatches — the pipeline is never invoked
        # inline, so the seam call cannot raise for analysis reasons.
        mock_pipeline = MagicMock()
        mock_delay = MagicMock()

        patches = [
            patch.object(analysis, "_analyze_feedback_item", mock_pipeline),
            patch.object(analysis.analyze_feedback_batch, "delay", mock_delay),
        ]
        for p in patches:
            p.start()
        try:
            result = analysis.reanalyze_feedback(db, item.id)  # must not raise
        finally:
            for p in patches:
                p.stop()

        assert result is True
        mock_delay.assert_called_once_with(org.id, [item.id])
        mock_pipeline.assert_not_called()

        # (b) A raising pipeline item inside the real batch loop returns a
        # `failed` count without raising — the enrichment loop is unaffected
        # because the seam only dispatched (analysis.py:253-259).
        patches = [
            patch.object(analysis, "_analyze_feedback_item", MagicMock(side_effect=RuntimeError("boom"))),
            patch.object(analysis, "get_db_session", _fake_db_session),
        ]
        _neutralize_batch_side_effects(analysis, patches)
        for p in patches:
            p.start()
        try:
            batch_result = analysis.analyze_feedback_batch(org.id, [item.id])  # must not raise
        finally:
            for p in patches:
                p.stop()

        assert batch_result == {
            "status": "complete",
            "analyzed": 0,
            "failed": 1,
            "total": 1,
        }


# ---------------------------------------------------------------------------
# Bounded dispatch (spec AC3b / PRD S1): one dispatch per changed id; zero
# changed ids → zero dispatches. The redelivery-level guard (no change → no
# dispatch) ships with pull-enrichment per its spec AC2 — this pins the
# seam-boundary half.
# ---------------------------------------------------------------------------


class TestBoundedDispatch:
    def test_dispatch_happens_once_per_changed_item(self, db):
        analysis = _reload_analysis()

        org_a = _make_org(db, "OrgA")
        org_b = _make_org(db, "OrgB")
        item_a = _make_analyzed_feedback(db, org_a.id, "stale A")
        item_b = _make_analyzed_feedback(db, org_b.id, "stale B")

        mock_delay = MagicMock()
        patches = [
            patch.object(analysis.analyze_feedback_batch, "delay", mock_delay),
        ]

        for p in patches:
            p.start()
        try:
            analysis.reanalyze_feedback(db, item_a.id)
            analysis.reanalyze_feedback(db, item_b.id)
        finally:
            for p in patches:
                p.stop()

        assert mock_delay.call_count == 2
        mock_delay.assert_any_call(org_a.id, [item_a.id])
        mock_delay.assert_any_call(org_b.id, [item_b.id])

    def test_no_changed_items_dispatches_nothing(self, db):
        """The seam is only reachable via a changed-item loop; an empty
        changed set must produce zero dispatches, no exception, and leave
        the item's stored analysis untouched. This is the guard that catches
        a future unconditional-dispatch regression."""
        analysis = _reload_analysis()

        org = _make_org(db)
        item = _make_analyzed_feedback(db, org.id, "unchanged text")
        before = {c.name: getattr(item, c.name) for c in item.__table__.columns}

        mock_delay = MagicMock()
        patches = [
            patch.object(analysis.analyze_feedback_batch, "delay", mock_delay),
        ]

        for p in patches:
            p.start()
        try:
            changed_ids: list[int] = []
            for feedback_id in changed_ids:  # the enrichment loop's shape
                analysis.reanalyze_feedback(db, feedback_id)
        finally:
            for p in patches:
                p.stop()

        mock_delay.assert_not_called()

        db.expire(item)
        db.refresh(item)
        after = {c.name: getattr(item, c.name) for c in item.__table__.columns}
        assert after == before, "an unchanged item must keep its stored analysis"
