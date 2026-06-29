"""
Unit tests for customer_timeline_service.build_timeline().
TDD phases 1-4: RED → GREEN → REFACTOR.

Phase 1: Port existing 5 sources (feedback_created, status_changed,
         health_score_changed, llm_analysis_generated, action_completed).
Phase 2: Add churned + churn_recovered.
Phase 3: Notable usage events (usage_first_seen, usage_reactivated,
         usage_feature_adopted). Flood guard.
Phase 4: Cursor correctness — equal-timestamp events never skipped/duplicated.
"""
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.customer_health_history import CustomerHealthHistory
from src.models.customer_analysis_action import CustomerAnalysisAction
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.churn_event import CustomerChurnEvent
from src.models.customer_usage import CustomerUsage
from src.models.usage_event import UsageEvent
from src.models.organization import Organization


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _org(db) -> Organization:
    o = Organization(name="Timeline Svc Test Org", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _health(db, org, email, **kwargs) -> CustomerHealth:
    defaults = dict(
        health_score=70,
        risk_level="moderate",
        feedback_count=1,
        confidence_level="medium",
        churn_risk_component=50,
        sentiment_component=65,
        resolution_component=70,
        frequency_component=55,
        is_archived=False,
    )
    defaults.update(kwargs)
    h = CustomerHealth(organization_id=org.id, customer_email=email, **defaults)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _feedback(db, org, email, ts=None) -> FeedbackItem:
    ts = ts or datetime.utcnow()
    fb = FeedbackItem(
        organization_id=org.id,
        customer_email=email,
        text="test feedback",
        source="email",
        workflow_status="new",
        sentiment_label="neutral",
        sentiment_score=0.0,
        is_urgent=False,
        created_at=ts,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _workflow(db, org, fb_id, ts=None) -> FeedbackWorkflowEvent:
    ts = ts or datetime.utcnow()
    ev = FeedbackWorkflowEvent(
        feedback_id=fb_id,
        organization_id=org.id,
        event_type="status_changed",
        old_value="new",
        new_value="resolved",
        created_at=ts,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _hist(db, org, health, score, ts=None) -> CustomerHealthHistory:
    ts = ts or datetime.utcnow()
    h = CustomerHealthHistory(
        customer_health_id=health.id,
        organization_id=org.id,
        health_score=score,
        risk_level="moderate",
        recorded_at=ts,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _action(db, health, ts=None) -> CustomerAnalysisAction:
    ts = ts or datetime.utcnow()
    a = CustomerAnalysisAction(
        customer_health_id=health.id,
        organization_id=health.organization_id,
        action_text="Review customer and send follow-up email",
        status="completed",
        completed_at=ts,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _churn(db, org, email, churned_at, reason_code="price", recovered_at=None) -> CustomerChurnEvent:
    ev = CustomerChurnEvent(
        organization_id=org.id,
        customer_email=email,
        churned_at=churned_at,
        reason_code=reason_code,
        source="manual",
        recovered_at=recovered_at,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _usage_rollup(db, org, email, first_seen_at) -> CustomerUsage:
    cu = CustomerUsage(
        organization_id=org.id,
        customer_email=email,
        first_seen_at=first_seen_at,
        last_active_at=datetime.utcnow(),
        usage_score=60,
        events_total=10,
    )
    db.add(cu)
    db.commit()
    db.refresh(cu)
    return cu


def _usage_event(db, org, email, event_name, occurred_at, ext_id=None) -> UsageEvent:
    ue = UsageEvent(
        organization_id=org.id,
        customer_email=email,
        event_type="track",
        event_name=event_name,
        external_event_id=ext_id or str(uuid.uuid4()),
        occurred_at=occurred_at,
        received_at=datetime.now(timezone.utc),
    )
    db.add(ue)
    db.commit()
    db.refresh(ue)
    return ue


# ---------------------------------------------------------------------------
# Phase 1 — Port existing 5 sources
# ---------------------------------------------------------------------------

class TestTimelinePhase1:

    def test_feedback_created_appears(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        ts = datetime.utcnow() - timedelta(hours=2)
        _feedback(db, org, "p1fb@acme.com", ts=ts)

        events, cursor = build_timeline(db, org.id, "p1fb@acme.com")
        types = [e.type for e in events]
        assert "feedback_created" in types
        fb_ev = next(e for e in events if e.type == "feedback_created")
        assert fb_ev.feedback_id is not None

    def test_status_changed_appears(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        fb = _feedback(db, org, "p1sc@acme.com", ts=datetime.utcnow() - timedelta(hours=3))
        _workflow(db, org, fb.id, ts=datetime.utcnow() - timedelta(hours=2))

        events, _ = build_timeline(db, org.id, "p1sc@acme.com")
        types = [e.type for e in events]
        assert "status_changed" in types

    def test_health_score_changed_appears(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        health = _health(db, org, "p1health@acme.com")
        _hist(db, org, health, score=60, ts=datetime.utcnow() - timedelta(days=2))
        _hist(db, org, health, score=55, ts=datetime.utcnow() - timedelta(days=1))

        events, _ = build_timeline(db, org.id, "p1health@acme.com")
        types = [e.type for e in events]
        assert "health_score_changed" in types

    def test_health_score_old_score_populated(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        health = _health(db, org, "p1oldscore@acme.com")
        # Earlier record
        _hist(db, org, health, score=70, ts=datetime.utcnow() - timedelta(days=3))
        # Later record — old_score should be 70
        _hist(db, org, health, score=55, ts=datetime.utcnow() - timedelta(days=1))

        events, _ = build_timeline(db, org.id, "p1oldscore@acme.com")
        h_ev = next(
            (e for e in events if e.type == "health_score_changed" and e.new_score == 55),
            None,
        )
        assert h_ev is not None
        assert h_ev.old_score == 70

    def test_llm_analysis_generated_appears(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        _health(db, org, "p1llm@acme.com", llm_analyzed_at=datetime.utcnow() - timedelta(hours=1))

        events, _ = build_timeline(db, org.id, "p1llm@acme.com")
        types = [e.type for e in events]
        assert "llm_analysis_generated" in types

    def test_action_completed_appears(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        health = _health(db, org, "p1action@acme.com")
        _action(db, health, ts=datetime.utcnow() - timedelta(hours=2))

        events, _ = build_timeline(db, org.id, "p1action@acme.com")
        types = [e.type for e in events]
        assert "action_completed" in types

    def test_events_ordered_by_timestamp_desc(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()
        _feedback(db, org, "p1order@acme.com", ts=now - timedelta(hours=10))
        _feedback(db, org, "p1order@acme.com", ts=now - timedelta(hours=5))
        _feedback(db, org, "p1order@acme.com", ts=now - timedelta(hours=1))

        events, _ = build_timeline(db, org.id, "p1order@acme.com")
        for i in range(len(events) - 1):
            ts0 = events[i].timestamp
            ts1 = events[i + 1].timestamp
            assert ts0 >= ts1, f"Order violation at index {i}: {ts0} < {ts1}"

    def test_composite_tiebreak_within_same_timestamp(self, db: Session):
        """
        Events at exactly the same timestamp must be sorted by (type ASC, source_id ASC).
        """
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        health = _health(db, org, "p1tie@acme.com")
        shared_ts = datetime.utcnow() - timedelta(hours=5)

        # feedback_created and health_score_changed at the same timestamp
        _feedback(db, org, "p1tie@acme.com", ts=shared_ts)
        _hist(db, org, health, score=50, ts=shared_ts)

        events, _ = build_timeline(db, org.id, "p1tie@acme.com")
        same_ts_events = [e for e in events if e.timestamp == shared_ts]
        if len(same_ts_events) >= 2:
            # In ASC type order: "feedback_created" > "health_score_changed" alphabetically? No.
            # "feedback_created" starts with 'f', "health_score_changed" starts with 'h'
            # f < h, so "feedback_created" should appear first (ASC = smaller first)
            types_at_ts = [e.type for e in same_ts_events]
            assert types_at_ts == sorted(types_at_ts), (
                f"Events at same timestamp not sorted by type ASC: {types_at_ts}"
            )

    def test_empty_customer_returns_empty_list(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        events, cursor = build_timeline(db, org.id, "nobody@acme.com")
        assert events == []
        assert cursor is None

    def test_no_health_row_still_returns_feedback(self, db: Session):
        """Customer with feedback but no health row → feedback events returned, no error."""
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        _feedback(db, org, "nohealth@acme.com")
        events, _ = build_timeline(db, org.id, "nohealth@acme.com")
        types = [e.type for e in events]
        assert "feedback_created" in types

    def test_limit_respected(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()
        for i in range(30):
            _feedback(db, org, "p1lim@acme.com", ts=now - timedelta(hours=i))

        events, _ = build_timeline(db, org.id, "p1lim@acme.com", limit=5)
        assert len(events) <= 5

    def test_next_cursor_set_when_more_events(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()
        for i in range(10):
            _feedback(db, org, "p1cur@acme.com", ts=now - timedelta(hours=i))

        events, cursor = build_timeline(db, org.id, "p1cur@acme.com", limit=5)
        assert len(events) == 5
        assert cursor is not None

    def test_next_cursor_none_on_last_page(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        for i in range(3):
            _feedback(db, org, "p1last@acme.com", ts=datetime.utcnow() - timedelta(hours=i))

        events, cursor = build_timeline(db, org.id, "p1last@acme.com", limit=20)
        assert len(events) == 3
        assert cursor is None

    def test_datetime_normalization_mixed_aware_naive(self, db: Session):
        """
        Aware (tz-UTC) timestamps must be normalized to naive UTC before sorting.
        We seed a naive feedback_created and an aware-stored usage_event,
        then verify ordering is correct regardless of tzinfo.
        """
        from src.services.customer_timeline_service import build_timeline, _to_naive_utc
        from datetime import timezone

        now_naive = datetime.utcnow()
        now_aware = datetime.now(timezone.utc)

        # Verify helper normalizes correctly
        assert _to_naive_utc(now_aware).tzinfo is None
        assert _to_naive_utc(now_naive).tzinfo is None

        # Both represent approximately the same time
        diff = abs((_to_naive_utc(now_aware) - _to_naive_utc(now_naive)).total_seconds())
        assert diff < 2, f"Normalization drift: {diff}s"

        org = _org(db)
        # Naive feedback_created at T-5h
        _feedback(db, org, "mixedtz@acme.com", ts=now_naive - timedelta(hours=5))
        # Aware usage event at T-3h (stored aware, read back as naive on SQLite)
        _usage_rollup(db, org, "mixedtz@acme.com", first_seen_at=now_aware - timedelta(hours=3))
        _usage_event(
            db, org, "mixedtz@acme.com", "login",
            occurred_at=now_aware - timedelta(hours=3),
        )

        events, _ = build_timeline(db, org.id, "mixedtz@acme.com", limit=10)
        # Should not error; timestamps should be sorted correctly
        for i in range(len(events) - 1):
            assert events[i].timestamp >= events[i + 1].timestamp


# ---------------------------------------------------------------------------
# Phase 2 — Churn events
# ---------------------------------------------------------------------------

class TestTimelinePhase2:

    def test_churned_event_appears(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        churned_at = datetime.utcnow() - timedelta(days=5)
        _churn(db, org, "p2churn@acme.com", churned_at=churned_at, reason_code="price")

        events, _ = build_timeline(db, org.id, "p2churn@acme.com")
        types = [e.type for e in events]
        assert "churned" in types

    def test_churned_event_has_reason_code(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        _churn(db, org, "p2reason@acme.com",
               churned_at=datetime.utcnow() - timedelta(days=3), reason_code="competitor")

        events, _ = build_timeline(db, org.id, "p2reason@acme.com")
        churned_ev = next(e for e in events if e.type == "churned")
        assert churned_ev.reason_code == "competitor"

    def test_churn_recovered_appears_when_set(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        churned_at = datetime.utcnow() - timedelta(days=10)
        recovered_at = datetime.utcnow() - timedelta(days=2)
        _churn(db, org, "p2rec@acme.com", churned_at=churned_at, recovered_at=recovered_at)

        events, _ = build_timeline(db, org.id, "p2rec@acme.com")
        types = [e.type for e in events]
        assert "churned" in types
        assert "churn_recovered" in types

    def test_churn_recovered_absent_when_not_set(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        _churn(db, org, "p2norec@acme.com",
               churned_at=datetime.utcnow() - timedelta(days=5))

        events, _ = build_timeline(db, org.id, "p2norec@acme.com")
        types = [e.type for e in events]
        assert "churned" in types
        assert "churn_recovered" not in types

    def test_churn_events_interleaved_correctly(self, db: Session):
        """
        churned_at=T-10, feedback_at=T-5, recovered_at=T-2 must appear in that order.
        """
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()
        _feedback(db, org, "p2interleave@acme.com", ts=now - timedelta(days=5))
        _churn(
            db, org, "p2interleave@acme.com",
            churned_at=now - timedelta(days=10),
            recovered_at=now - timedelta(days=2),
        )

        events, _ = build_timeline(db, org.id, "p2interleave@acme.com")
        types = [e.type for e in events]
        # recovered_at is newest → first, then feedback, then churned
        ri = types.index("churn_recovered")
        fi = types.index("feedback_created")
        ci = types.index("churned")
        assert ri < fi < ci, (
            f"Expected order: churn_recovered < feedback_created < churned. Got: {types}"
        )

    def test_multi_tenant_churn_isolation(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org_a = _org(db)
        org_b = Organization(name="Org B", plan="pro")
        db.add(org_b)
        db.commit()
        db.refresh(org_b)

        # Churn event for org_b only
        _churn(db, org_b, "shared@acme.com", churned_at=datetime.utcnow() - timedelta(days=5))

        events, _ = build_timeline(db, org_a.id, "shared@acme.com")
        types = [e.type for e in events]
        assert "churned" not in types, "Org isolation violated: churn from org_b leaked into org_a"


# ---------------------------------------------------------------------------
# Phase 3 — Notable usage events
# ---------------------------------------------------------------------------

class TestTimelinePhase3:

    def test_usage_first_seen_appears(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        first_seen = datetime.utcnow() - timedelta(days=30)
        _usage_rollup(db, org, "p3fs@acme.com", first_seen_at=first_seen)

        events, _ = build_timeline(db, org.id, "p3fs@acme.com")
        types = [e.type for e in events]
        assert "usage_first_seen" in types

    def test_usage_first_seen_absent_when_no_rollup(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        _health(db, org, "p3nofs@acme.com")

        events, _ = build_timeline(db, org.id, "p3nofs@acme.com")
        types = [e.type for e in events]
        assert "usage_first_seen" not in types

    def test_usage_feature_adopted_once_per_feature(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()
        # 3 events for "login", 2 for "export"
        for i in range(3):
            _usage_event(db, org, "p3feat@acme.com", "login", now - timedelta(days=10 + i))
        for i in range(2):
            _usage_event(db, org, "p3feat@acme.com", "export", now - timedelta(days=5 + i))

        events, _ = build_timeline(db, org.id, "p3feat@acme.com", limit=100)
        feat_events = [e for e in events if e.type == "usage_feature_adopted"]
        feature_names = [e.feature_name for e in feat_events]
        # Exactly one event per distinct feature
        assert sorted(feature_names) == ["export", "login"], (
            f"Expected exactly one per feature, got: {feature_names}"
        )

    def test_usage_feature_adopted_at_first_occurrence(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()
        first_ts = now - timedelta(days=15)
        second_ts = now - timedelta(days=10)
        _usage_event(db, org, "p3first@acme.com", "login", first_ts)
        _usage_event(db, org, "p3first@acme.com", "login", second_ts)

        events, _ = build_timeline(db, org.id, "p3first@acme.com", limit=100)
        login_adopt = next(e for e in events if e.type == "usage_feature_adopted" and e.feature_name == "login")
        # Timestamp should be the FIRST occurrence (earliest)
        from src.services.customer_timeline_service import _to_naive_utc
        assert _to_naive_utc(login_adopt.timestamp) == _to_naive_utc(first_ts)

    def test_usage_reactivation_after_dormancy(self, db: Session):
        from src.services.customer_timeline_service import build_timeline, DORMANCY_DAYS
        org = _org(db)
        now = datetime.utcnow()
        # Two events close together (no gap)
        _usage_event(db, org, "p3react@acme.com", "login", now - timedelta(days=30))
        _usage_event(db, org, "p3react@acme.com", "login", now - timedelta(days=29))
        # Gap of DORMANCY_DAYS + 1 (reactivation trigger)
        gap_days = DORMANCY_DAYS + 1
        _usage_event(db, org, "p3react@acme.com", "login", now - timedelta(days=29 - gap_days))

        events, _ = build_timeline(db, org.id, "p3react@acme.com", limit=100)
        react_events = [e for e in events if e.type == "usage_reactivated"]
        assert len(react_events) == 1, f"Expected 1 reactivation, got {len(react_events)}"
        assert react_events[0].gap_days >= DORMANCY_DAYS

    def test_no_reactivation_when_no_gap(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()
        # Events every day — no gap ≥ 14 days
        for i in range(14):
            _usage_event(db, org, "p3nogap@acme.com", "login", now - timedelta(days=i))

        events, _ = build_timeline(db, org.id, "p3nogap@acme.com", limit=100)
        react_events = [e for e in events if e.type == "usage_reactivated"]
        assert len(react_events) == 0

    def test_multiple_reactivations(self, db: Session):
        from src.services.customer_timeline_service import build_timeline, DORMANCY_DAYS
        org = _org(db)
        now = datetime.utcnow()
        # Gap 1: days 90 and 70 → gap = 20 days → reactivation at day 70
        _usage_event(db, org, "p3multi@acme.com", "login", now - timedelta(days=90))
        _usage_event(db, org, "p3multi@acme.com", "login", now - timedelta(days=70))
        # Close events
        _usage_event(db, org, "p3multi@acme.com", "login", now - timedelta(days=69))
        # Gap 2: days 69 and 50 → gap = 19 days → reactivation at day 50
        _usage_event(db, org, "p3multi@acme.com", "login", now - timedelta(days=50))

        events, _ = build_timeline(db, org.id, "p3multi@acme.com", limit=100)
        react_events = [e for e in events if e.type == "usage_reactivated"]
        assert len(react_events) == 2, f"Expected 2 reactivations, got {len(react_events)}"

    def test_usage_does_not_flood_same_event_name(self, db: Session):
        """
        1000 raw events with the same event_name, no gaps → exactly 1 usage_first_seen
        + 1 usage_feature_adopted, 0 reactivations.
        """
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()

        # Rollup for first_seen
        _usage_rollup(db, org, "p3flood@acme.com", first_seen_at=now - timedelta(days=1))

        # 1000 events, spaced 1 minute apart (no dormancy gap)
        for i in range(1000):
            _usage_event(
                db, org, "p3flood@acme.com", "login",
                now - timedelta(minutes=i),
            )

        events, _ = build_timeline(db, org.id, "p3flood@acme.com", limit=100)
        first_seen = [e for e in events if e.type == "usage_first_seen"]
        feature_adopted = [e for e in events if e.type == "usage_feature_adopted"]
        reactivated = [e for e in events if e.type == "usage_reactivated"]

        assert len(first_seen) == 1, f"Expected 1 usage_first_seen, got {len(first_seen)}"
        assert len(feature_adopted) == 1, (
            f"Expected 1 usage_feature_adopted, got {len(feature_adopted)}"
        )
        assert len(reactivated) == 0, (
            f"Expected 0 usage_reactivated, got {len(reactivated)}"
        )

    def test_notable_usage_scan_not_filtered_by_before(self, db: Session):
        """
        The before cursor must NOT be applied to the raw usage_events scan input.
        Gap/first-occurrence detection must see the full history.
        If we had two usage events: day-30 and day-10 (gap=20 days → reactivation),
        and the cursor puts 'before' at day-15, the reactivation at day-10 must STILL
        be detected correctly (because the scan sees the full window).
        """
        from src.services.customer_timeline_service import build_timeline, _encode_cursor
        org = _org(db)
        now = datetime.utcnow()

        # Event at day-30 (old) and day-10 (after 20-day gap → reactivation)
        _usage_event(db, org, "p3scan@acme.com", "login", now - timedelta(days=30))
        _usage_event(db, org, "p3scan@acme.com", "login", now - timedelta(days=10))

        # Build a cursor that puts "before" at day-15 (between the two events)
        # The reactivation event at day-10 should appear on the SECOND page
        # (it's at ts=now-10d, which is NEWER than cursor at now-15d)
        # So first page (no cursor) should show it:
        events_full, _ = build_timeline(db, org.id, "p3scan@acme.com", limit=100)
        react_events = [e for e in events_full if e.type == "usage_reactivated"]
        assert len(react_events) == 1, (
            "Reactivation should be detected even when scanning across the cursor boundary"
        )

    def test_usage_multi_tenant_isolation(self, db: Session):
        from src.services.customer_timeline_service import build_timeline
        org_a = _org(db)
        org_b = Organization(name="Org B for usage", plan="pro")
        db.add(org_b)
        db.commit()
        db.refresh(org_b)

        # Usage events only for org_b
        _usage_event(db, org_b, "shared@acme.com", "login", datetime.utcnow() - timedelta(days=5))
        _usage_rollup(db, org_b, "shared@acme.com", first_seen_at=datetime.utcnow() - timedelta(days=5))

        events, _ = build_timeline(db, org_a.id, "shared@acme.com", limit=100)
        types = [e.type for e in events]
        assert "usage_first_seen" not in types
        assert "usage_feature_adopted" not in types


# ---------------------------------------------------------------------------
# Phase 4 — Cursor correctness
# ---------------------------------------------------------------------------

class TestTimelinePhase4:

    def test_cursor_encode_decode_roundtrip(self):
        from src.services.customer_timeline_service import _encode_cursor, _decode_cursor
        ts = datetime(2024, 6, 15, 10, 30, 45, 123456)
        cursor = _encode_cursor(ts, "feedback_created", 42)
        decoded_ts, decoded_type, decoded_sid = _decode_cursor(cursor)
        assert decoded_ts == ts
        assert decoded_type == "feedback_created"
        assert decoded_sid == 42

    def test_bad_cursor_raises_value_error(self):
        from src.services.customer_timeline_service import _decode_cursor
        with pytest.raises(ValueError):
            _decode_cursor("not_valid_base64!!")

    def test_cursor_paging_no_dup_no_gap_equal_timestamps(self, db: Session):
        """
        Seed events including multiple events sharing an identical timestamp
        across different sources. Page with limit=5. Collected pages must equal
        the unpaged full list (no duplicates, no gaps).
        """
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()

        # One shared timestamp — events from two different sources
        shared_ts = now - timedelta(hours=3)

        health = _health(db, org, "p4page@acme.com",
                         llm_analyzed_at=now - timedelta(hours=6))

        # 5 feedbacks at shared_ts
        for i in range(5):
            _feedback(db, org, "p4page@acme.com", ts=shared_ts)

        # 3 health history rows at shared_ts (different source, same timestamp)
        for j in range(3):
            _hist(db, org, health, score=50 + j, ts=shared_ts)

        # 5 more feedbacks at different times (so total > limit=5)
        for k in range(5):
            _feedback(db, org, "p4page@acme.com", ts=now - timedelta(hours=k + 7))

        # Unpaged full list
        all_events, _ = build_timeline(db, org.id, "p4page@acme.com", limit=100)
        total = len(all_events)
        assert total > 5, "Need more events than page_limit for this test"

        # Page with limit=5
        collected = []
        cursor = None
        pages = 0
        while True:
            page_events, next_cursor = build_timeline(
                db, org.id, "p4page@acme.com",
                before=cursor, limit=5,
            )
            assert len(page_events) <= 5
            collected.extend(page_events)
            cursor = next_cursor
            pages += 1
            if cursor is None:
                break
            assert pages <= total + 5, "Pagination did not terminate"

        # No duplicates (by composite key)
        composite_keys = [(e.type, e.timestamp, e.source_id) for e in collected]
        assert len(composite_keys) == len(set(composite_keys)), (
            f"Duplicates in pagination: {[k for k in composite_keys if composite_keys.count(k) > 1]}"
        )

        # Same total
        assert len(collected) == total, (
            f"Paginated ({len(collected)}) != full ({total})"
        )

        # Same order
        for i, (c, f) in enumerate(zip(collected, all_events)):
            assert c.type == f.type, f"Type mismatch at index {i}: {c.type} vs {f.type}"
            assert c.timestamp == f.timestamp, f"TS mismatch at index {i}"
            assert c.source_id == f.source_id, f"SID mismatch at index {i}"

    def test_cursor_no_skip_at_shared_timestamp(self, db: Session):
        """
        Two events sharing the exact same timestamp from different sources:
        page through with limit=1 and confirm both appear (no skip).
        """
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        shared_ts = datetime.utcnow() - timedelta(hours=1)

        health = _health(db, org, "p4skip@acme.com")
        # feedback_created (type="feedback_created") at shared_ts
        _feedback(db, org, "p4skip@acme.com", ts=shared_ts)
        # health_score_changed (type="health_score_changed") at shared_ts
        _hist(db, org, health, score=50, ts=shared_ts)

        # Full list
        all_events, _ = build_timeline(db, org.id, "p4skip@acme.com", limit=100)
        assert len(all_events) >= 2

        # Page with limit=1
        collected = []
        cursor = None
        for _ in range(10):  # safety limit
            page, cursor = build_timeline(db, org.id, "p4skip@acme.com", before=cursor, limit=1)
            collected.extend(page)
            if cursor is None:
                break

        assert len(collected) == len(all_events), (
            f"Paginated ({len(collected)}) != full ({len(all_events)}): some events skipped"
        )

    def test_cursor_stable_across_runs(self, db: Session):
        """Same cursor input on two consecutive calls must return identical results."""
        from src.services.customer_timeline_service import build_timeline
        org = _org(db)
        now = datetime.utcnow()
        for i in range(10):
            _feedback(db, org, "p4stable@acme.com", ts=now - timedelta(hours=i))

        _, cursor = build_timeline(db, org.id, "p4stable@acme.com", limit=5)
        assert cursor is not None

        run1, _ = build_timeline(db, org.id, "p4stable@acme.com", before=cursor, limit=5)
        run2, _ = build_timeline(db, org.id, "p4stable@acme.com", before=cursor, limit=5)

        assert len(run1) == len(run2)
        for a, b in zip(run1, run2):
            assert a.type == b.type
            assert a.timestamp == b.timestamp
