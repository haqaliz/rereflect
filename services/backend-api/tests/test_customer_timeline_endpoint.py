"""
Tests for customer timeline endpoints:
  Phase 0: Characterization test — locks /activity contract before refactor.
  Phase 5: Tests for new GET /api/v1/customers/{email}/timeline endpoint.
  Phase 6: usage_trend_change on the internal /timeline AND the public
           /api/public/v1/customers/{email}/timeline mirror (timeline-trend-event).
"""
import base64
import hashlib
import secrets
import pytest
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.customer_health import CustomerHealth
from src.models.customer_health_history import CustomerHealthHistory
from src.models.customer_analysis_action import CustomerAnalysisAction
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.churn_event import CustomerChurnEvent
from src.models.customer_usage import CustomerUsage
from src.models.usage_event import UsageEvent
from src.models.customer_usage_history import CustomerUsageHistory
from src.models.api_key import ApiKey
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures (mirror test_customer_profile.py patterns)
# ---------------------------------------------------------------------------

@pytest.fixture
def tl_org(db: Session) -> Organization:
    org = Organization(name="Timeline Test Org", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def tl_user(db: Session, tl_org: Organization) -> User:
    user = User(
        email="timeline@example.com",
        password_hash=hash_password("password123"),
        organization_id=tl_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def tl_headers(tl_user: User) -> dict:
    token = create_access_token({
        "user_id": tl_user.id,
        "organization_id": tl_user.organization_id,
        "role": tl_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def _make_health(db, org, email, **kwargs) -> CustomerHealth:
    now = datetime.utcnow()
    defaults = dict(
        health_score=70,
        risk_level="moderate",
        feedback_count=3,
        confidence_level="medium",
        churn_risk_component=50,
        sentiment_component=65,
        resolution_component=70,
        frequency_component=55,
        last_feedback_at=now,
        is_archived=False,
    )
    defaults.update(kwargs)
    h = CustomerHealth(organization_id=org.id, customer_email=email, **defaults)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _make_feedback(db, org, email, text="test feedback", offset_hours=0) -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org.id,
        customer_email=email,
        text=text,
        source="email",
        workflow_status="new",
        sentiment_label="neutral",
        sentiment_score=0.0,
        is_urgent=False,
        created_at=datetime.utcnow() - timedelta(hours=offset_hours),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _make_workflow_event(db, org, feedback_id, offset_hours=0) -> FeedbackWorkflowEvent:
    ev = FeedbackWorkflowEvent(
        feedback_id=feedback_id,
        organization_id=org.id,
        event_type="status_changed",
        old_value="new",
        new_value="resolved",
        created_at=datetime.utcnow() - timedelta(hours=offset_hours),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _make_health_history(db, org, health, score, offset_days=0) -> CustomerHealthHistory:
    hist = CustomerHealthHistory(
        customer_health_id=health.id,
        organization_id=org.id,
        health_score=score,
        risk_level="moderate",
        recorded_at=datetime.utcnow() - timedelta(days=offset_days),
    )
    db.add(hist)
    db.commit()
    db.refresh(hist)
    return hist


def _make_action(db, health, text="Review customer", offset_hours=0) -> CustomerAnalysisAction:
    action = CustomerAnalysisAction(
        customer_health_id=health.id,
        organization_id=health.organization_id,
        action_text=text,
        status="completed",
        completed_at=datetime.utcnow() - timedelta(hours=offset_hours),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def _make_churn_event(
    db, org, email, reason_code="price", offset_days=5, recovered=False
) -> CustomerChurnEvent:
    churned_at = datetime.utcnow() - timedelta(days=offset_days)
    recovered_at = (datetime.utcnow() - timedelta(days=2)) if recovered else None
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


def _make_usage_rollup(db, org, email, first_seen_days_ago=30) -> CustomerUsage:
    first_seen = datetime.utcnow() - timedelta(days=first_seen_days_ago)
    cu = CustomerUsage(
        organization_id=org.id,
        customer_email=email,
        first_seen_at=first_seen,
        last_active_at=datetime.utcnow() - timedelta(days=1),
        usage_score=60,
        events_total=10,
    )
    db.add(cu)
    db.commit()
    db.refresh(cu)
    return cu


def _make_usage_event(
    db, org, email, event_name="login", offset_days=0, ext_id=None
) -> UsageEvent:
    import uuid
    ue = UsageEvent(
        organization_id=org.id,
        customer_email=email,
        event_type="track",
        event_name=event_name,
        external_event_id=ext_id or str(uuid.uuid4()),
        occurred_at=datetime.now(timezone.utc) - timedelta(days=offset_days),
        received_at=datetime.now(timezone.utc),
    )
    db.add(ue)
    db.commit()
    db.refresh(ue)
    return ue


def _make_usage_snapshot(
    db, org, email, snapshot_date, trend_state=None, trend_pct=None
) -> CustomerUsageHistory:
    row = CustomerUsageHistory(
        organization_id=org.id,
        customer_email=email,
        snapshot_date=snapshot_date,
        usage_trend_state=trend_state,
        usage_trend_pct=trend_pct,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_api_key(db: Session, org_id: int, scopes: str = "read") -> str:
    """Create a stored ApiKey row and return the raw key."""
    raw = f"rrf_{secrets.token_urlsafe(24)}"
    row = ApiKey(
        organization_id=org_id,
        name="test key",
        key_prefix=raw[:10],
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        scopes=scopes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw


# ---------------------------------------------------------------------------
# Phase 0 — Characterization: existing /activity contract
# ---------------------------------------------------------------------------

class TestActivityCharacterization:
    """
    Locks the /activity endpoint's external contract before we refactor its
    internals in Phase 5. These tests MUST stay green through all phases.
    """

    def test_activity_returns_200(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "char@acme.com")
        resp = client.get("/api/v1/customers/char@acme.com/activity", headers=tl_headers)
        assert resp.status_code == 200

    def test_activity_has_events_list(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "charfield@acme.com")
        resp = client.get("/api/v1/customers/charfield@acme.com/activity", headers=tl_headers)
        data = resp.json()
        assert "events" in data
        assert isinstance(data["events"], list)
        # Legacy shape must NOT have next_cursor (activity is not paginated)
        assert "next_cursor" not in data

    def test_activity_includes_feedback_created(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "charfb@acme.com")
        _make_feedback(db, tl_org, "charfb@acme.com")
        resp = client.get("/api/v1/customers/charfb@acme.com/activity", headers=tl_headers)
        types = [e["type"] for e in resp.json()["events"]]
        assert "feedback_created" in types

    def test_activity_includes_status_changed(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "charstatus@acme.com")
        fb = _make_feedback(db, tl_org, "charstatus@acme.com")
        _make_workflow_event(db, tl_org, fb.id)
        resp = client.get("/api/v1/customers/charstatus@acme.com/activity", headers=tl_headers)
        types = [e["type"] for e in resp.json()["events"]]
        assert "status_changed" in types

    def test_activity_includes_health_score_changed(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        health = _make_health(db, tl_org, "charhist@acme.com")
        _make_health_history(db, tl_org, health, score=55, offset_days=3)
        resp = client.get("/api/v1/customers/charhist@acme.com/activity", headers=tl_headers)
        types = [e["type"] for e in resp.json()["events"]]
        assert "health_score_changed" in types

    def test_activity_includes_llm_analysis_generated(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "charllm@acme.com",
                     llm_analyzed_at=datetime.utcnow() - timedelta(hours=2))
        resp = client.get("/api/v1/customers/charllm@acme.com/activity", headers=tl_headers)
        types = [e["type"] for e in resp.json()["events"]]
        assert "llm_analysis_generated" in types

    def test_activity_includes_action_completed(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        health = _make_health(db, tl_org, "charaction@acme.com")
        _make_action(db, health, offset_hours=1)
        resp = client.get("/api/v1/customers/charaction@acme.com/activity", headers=tl_headers)
        types = [e["type"] for e in resp.json()["events"]]
        assert "action_completed" in types

    def test_activity_events_ordered_desc(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "charord@acme.com")
        _make_feedback(db, tl_org, "charord@acme.com", offset_hours=10)  # older
        _make_feedback(db, tl_org, "charord@acme.com", offset_hours=1)   # newer
        resp = client.get("/api/v1/customers/charord@acme.com/activity", headers=tl_headers)
        events = resp.json()["events"]
        if len(events) >= 2:
            ts0 = datetime.fromisoformat(events[0]["timestamp"].rstrip("Z"))
            ts1 = datetime.fromisoformat(events[1]["timestamp"].rstrip("Z"))
            assert ts0 >= ts1, "Events must be ordered newest-first"

    def test_activity_max_10_events(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "charmax@acme.com")
        for i in range(15):
            _make_feedback(db, tl_org, "charmax@acme.com", offset_hours=i)
        resp = client.get("/api/v1/customers/charmax@acme.com/activity", headers=tl_headers)
        assert len(resp.json()["events"]) <= 10

    def test_activity_event_fields(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "charfields@acme.com")
        _make_feedback(db, tl_org, "charfields@acme.com")
        resp = client.get("/api/v1/customers/charfields@acme.com/activity", headers=tl_headers)
        event = resp.json()["events"][0]
        assert "type" in event
        assert "description" in event
        assert "timestamp" in event

    def test_activity_free_plan_403(self, client: TestClient, db: Session):
        """Free plan can't access /activity."""
        free_org = Organization(name="Free Org", plan="free")
        db.add(free_org)
        db.commit()
        db.refresh(free_org)
        user = User(
            email="free@example.com",
            password_hash=hash_password("pass"),
            organization_id=free_org.id,
            role="admin",
        )
        db.add(user)
        db.commit()
        token = create_access_token({"user_id": user.id, "organization_id": free_org.id, "role": user.role})
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/customers/anyone@example.com/activity", headers=headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Phase 5 — New GET /customers/{email}/timeline endpoint
# ---------------------------------------------------------------------------

class TestTimelineEndpoint:

    def test_timeline_returns_200(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tl200@acme.com")
        _make_feedback(db, tl_org, "tl200@acme.com")
        resp = client.get("/api/v1/customers/tl200@acme.com/timeline", headers=tl_headers)
        assert resp.status_code == 200

    def test_timeline_response_shape(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tlshape@acme.com")
        _make_feedback(db, tl_org, "tlshape@acme.com")
        resp = client.get("/api/v1/customers/tlshape@acme.com/timeline", headers=tl_headers)
        data = resp.json()
        assert "events" in data
        assert "next_cursor" in data

    def test_timeline_unknown_customer_returns_empty(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        """Unknown customer → empty list (same precedent as /history)."""
        resp = client.get("/api/v1/customers/nobody@unknown.com/timeline", headers=tl_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["next_cursor"] is None

    def test_timeline_default_limit_20(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tllimit@acme.com")
        for i in range(25):
            _make_feedback(db, tl_org, "tllimit@acme.com", offset_hours=i)
        resp = client.get("/api/v1/customers/tllimit@acme.com/timeline", headers=tl_headers)
        data = resp.json()
        assert len(data["events"]) <= 20

    def test_timeline_limit_param(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tllimitp@acme.com")
        for i in range(10):
            _make_feedback(db, tl_org, "tllimitp@acme.com", offset_hours=i)
        resp = client.get("/api/v1/customers/tllimitp@acme.com/timeline?limit=3", headers=tl_headers)
        data = resp.json()
        assert len(data["events"]) <= 3

    def test_timeline_limit_0_returns_422(
        self, client: TestClient, tl_headers: dict
    ):
        resp = client.get("/api/v1/customers/x@x.com/timeline?limit=0", headers=tl_headers)
        assert resp.status_code == 422

    def test_timeline_limit_101_returns_422(
        self, client: TestClient, tl_headers: dict
    ):
        resp = client.get("/api/v1/customers/x@x.com/timeline?limit=101", headers=tl_headers)
        assert resp.status_code == 422

    def test_timeline_bad_before_returns_422(
        self, client: TestClient, tl_headers: dict
    ):
        resp = client.get(
            "/api/v1/customers/x@x.com/timeline?before=NOT_VALID_BASE64%%",
            headers=tl_headers
        )
        assert resp.status_code == 422

    def test_timeline_future_before_is_valid(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        """A valid cursor encoding a future timestamp is technically valid (returns empty or earlier events)."""
        from src.services.customer_timeline_service import _encode_cursor
        future_ts = datetime.utcnow() + timedelta(days=365)
        cursor = _encode_cursor(future_ts, "feedback_created", 1)
        _make_health(db, tl_org, "tlfuture@acme.com")
        _make_feedback(db, tl_org, "tlfuture@acme.com", offset_hours=1)
        resp = client.get(
            f"/api/v1/customers/tlfuture@acme.com/timeline?before={cursor}",
            headers=tl_headers,
        )
        # A future cursor means "show everything before this future ts" which includes all events
        assert resp.status_code == 200

    def test_timeline_includes_all_event_types(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        """All 10 event types appear when the data is present."""
        health = _make_health(db, tl_org, "tltypes@acme.com",
                              llm_analyzed_at=datetime.utcnow() - timedelta(hours=3))
        fb = _make_feedback(db, tl_org, "tltypes@acme.com", offset_hours=5)
        _make_workflow_event(db, tl_org, fb.id, offset_hours=4)
        _make_health_history(db, tl_org, health, score=60, offset_days=2)
        _make_action(db, health, offset_hours=6)
        _make_churn_event(db, tl_org, "tltypes@acme.com", offset_days=10, recovered=True)
        _make_usage_rollup(db, tl_org, "tltypes@acme.com", first_seen_days_ago=20)
        # Usage events: first_seen + reactivation + feature_adopted
        _make_usage_event(db, tl_org, "tltypes@acme.com", event_name="login", offset_days=20)
        _make_usage_event(db, tl_org, "tltypes@acme.com", event_name="login", offset_days=19)
        _make_usage_event(db, tl_org, "tltypes@acme.com", event_name="export", offset_days=3)  # feature adopted
        # Gap: 19 days between day-19 and day-3 (>= 14) → reactivation
        _make_usage_event(db, tl_org, "tltypes@acme.com", event_name="login", offset_days=2)

        resp = client.get("/api/v1/customers/tltypes@acme.com/timeline?limit=100", headers=tl_headers)
        assert resp.status_code == 200
        types = {e["type"] for e in resp.json()["events"]}
        assert "feedback_created" in types
        assert "status_changed" in types
        assert "health_score_changed" in types
        assert "llm_analysis_generated" in types
        assert "action_completed" in types
        assert "churned" in types
        assert "churn_recovered" in types
        assert "usage_first_seen" in types
        assert "usage_feature_adopted" in types
        assert "usage_reactivated" in types

    def test_timeline_events_ordered_desc(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tlord@acme.com")
        _make_feedback(db, tl_org, "tlord@acme.com", offset_hours=10)
        _make_feedback(db, tl_org, "tlord@acme.com", offset_hours=1)
        resp = client.get("/api/v1/customers/tlord@acme.com/timeline", headers=tl_headers)
        events = resp.json()["events"]
        for i in range(len(events) - 1):
            ts0 = datetime.fromisoformat(events[i]["timestamp"].rstrip("Z"))
            ts1 = datetime.fromisoformat(events[i + 1]["timestamp"].rstrip("Z"))
            assert ts0 >= ts1, f"Event {i} is not >= event {i+1} in timestamp DESC order"

    def test_timeline_next_cursor_present_when_more(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tlcursor@acme.com")
        for i in range(25):
            _make_feedback(db, tl_org, "tlcursor@acme.com", offset_hours=i)
        resp = client.get("/api/v1/customers/tlcursor@acme.com/timeline?limit=5", headers=tl_headers)
        data = resp.json()
        assert len(data["events"]) == 5
        assert data["next_cursor"] is not None

    def test_timeline_next_cursor_null_last_page(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tllast@acme.com")
        for i in range(3):
            _make_feedback(db, tl_org, "tllast@acme.com", offset_hours=i)
        resp = client.get("/api/v1/customers/tllast@acme.com/timeline?limit=20", headers=tl_headers)
        data = resp.json()
        assert len(data["events"]) == 3
        assert data["next_cursor"] is None

    def test_timeline_pagination_no_dup_no_gap(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        """
        Phase 4 correctness: page through all events including events sharing
        identical timestamps across sources. Full concatenation must equal unpaged list.
        """
        health = _make_health(db, tl_org, "tlpagegap@acme.com",
                              llm_analyzed_at=datetime.utcnow() - timedelta(hours=5))

        # Fixed timestamp for cross-source collision
        shared_ts = datetime.utcnow() - timedelta(hours=2)

        # Two feedback items at the SAME timestamp (cross-source collision via health history + feedback)
        for i in range(8):
            fb = FeedbackItem(
                organization_id=tl_org.id,
                customer_email="tlpagegap@acme.com",
                text=f"FB {i}",
                source="email",
                workflow_status="new",
                sentiment_label="neutral",
                sentiment_score=0.0,
                is_urgent=False,
                created_at=shared_ts,  # all same timestamp
            )
            db.add(fb)
        db.commit()

        # Health history rows at the SAME shared_ts (cross-source collision)
        for j in range(3):
            hist = CustomerHealthHistory(
                customer_health_id=health.id,
                organization_id=tl_org.id,
                health_score=50 + j,
                risk_level="moderate",
                recorded_at=shared_ts,  # same timestamp
            )
            db.add(hist)
        db.commit()

        # Get unpaged full list
        resp_full = client.get(
            "/api/v1/customers/tlpagegap@acme.com/timeline?limit=100",
            headers=tl_headers,
        )
        assert resp_full.status_code == 200
        full_events = resp_full.json()["events"]
        total = len(full_events)
        assert total > 0

        # Page through with small limit
        page_limit = 4
        collected = []
        cursor = None
        pages = 0
        while True:
            url = f"/api/v1/customers/tlpagegap@acme.com/timeline?limit={page_limit}"
            if cursor:
                url += f"&before={cursor}"
            resp = client.get(url, headers=tl_headers)
            assert resp.status_code == 200
            data = resp.json()
            events = data["events"]
            assert len(events) <= page_limit
            collected.extend(events)
            cursor = data["next_cursor"]
            pages += 1
            if cursor is None:
                break
            assert pages <= total + 5, "Pagination must terminate"

        # Same total count as unpaged
        assert len(collected) == total, (
            f"Paginated total ({len(collected)}) != unpaged total ({total})"
        )

        # Same order as unpaged
        for i, (paged, full) in enumerate(zip(collected, full_events)):
            assert paged["type"] == full["type"], f"Mismatch at index {i}: {paged} vs {full}"
            assert paged["timestamp"] == full["timestamp"], f"Timestamp mismatch at index {i}"

    def test_timeline_cross_org_isolation(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        """Events from another org must never appear in the timeline."""
        other_org = Organization(name="Other Org", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        # Our org: one feedback
        _make_health(db, tl_org, "isolated@acme.com")
        _make_feedback(db, tl_org, "isolated@acme.com")

        # Other org: also has events for the same email
        _make_feedback(db, other_org, "isolated@acme.com")
        _make_churn_event(db, other_org, "isolated@acme.com")

        resp = client.get(
            "/api/v1/customers/isolated@acme.com/timeline?limit=100",
            headers=tl_headers,
        )
        assert resp.status_code == 200
        events = resp.json()["events"]

        # All events must be for tl_org only — we verify by checking count (1 feedback + 0 cross-org)
        # There should be exactly 1 feedback_created event (only from tl_org)
        fb_events = [e for e in events if e["type"] == "feedback_created"]
        assert len(fb_events) == 1, "Cross-org event leaked into timeline"
        # No churned events from other_org
        churn_events = [e for e in events if e["type"] == "churned"]
        assert len(churn_events) == 0

    def test_timeline_churn_events_present(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tlchurn@acme.com")
        _make_churn_event(db, tl_org, "tlchurn@acme.com", reason_code="price", recovered=True)
        resp = client.get(
            "/api/v1/customers/tlchurn@acme.com/timeline?limit=100",
            headers=tl_headers,
        )
        types = {e["type"] for e in resp.json()["events"]}
        assert "churned" in types
        assert "churn_recovered" in types

    def test_timeline_churn_event_has_reason_code(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tlreason@acme.com")
        _make_churn_event(db, tl_org, "tlreason@acme.com", reason_code="competitor")
        resp = client.get(
            "/api/v1/customers/tlreason@acme.com/timeline?limit=100",
            headers=tl_headers,
        )
        churn_ev = next(e for e in resp.json()["events"] if e["type"] == "churned")
        assert churn_ev.get("reason_code") == "competitor"

    def test_timeline_usage_events_present(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "tlusage@acme.com")
        _make_usage_rollup(db, tl_org, "tlusage@acme.com", first_seen_days_ago=30)
        _make_usage_event(db, tl_org, "tlusage@acme.com", event_name="login", offset_days=30)
        _make_usage_event(db, tl_org, "tlusage@acme.com", event_name="export", offset_days=29)
        # Gap ≥ 14 → reactivation
        _make_usage_event(db, tl_org, "tlusage@acme.com", event_name="login", offset_days=10)
        resp = client.get(
            "/api/v1/customers/tlusage@acme.com/timeline?limit=100",
            headers=tl_headers,
        )
        types = {e["type"] for e in resp.json()["events"]}
        assert "usage_first_seen" in types
        assert "usage_feature_adopted" in types
        assert "usage_reactivated" in types

    def test_timeline_free_plan_returns_403(
        self, client: TestClient, db: Session
    ):
        free_org = Organization(name="Free Org 2", plan="free")
        db.add(free_org)
        db.commit()
        db.refresh(free_org)
        user = User(
            email="free2@example.com",
            password_hash=hash_password("pass"),
            organization_id=free_org.id,
            role="admin",
        )
        db.add(user)
        db.commit()
        token = create_access_token({"user_id": user.id, "organization_id": free_org.id, "role": user.role})
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/customers/x@x.com/timeline", headers=headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Phase 6 — usage_trend_change on the internal /timeline AND the public mirror
# (timeline-trend-event aspect)
# ---------------------------------------------------------------------------

class TestTimelineUsageTrendEvent:

    def test_usage_trend_change_appears_on_internal_timeline(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        _make_health(db, tl_org, "utrend@acme.com")
        _make_usage_snapshot(db, tl_org, "utrend@acme.com", date(2026, 7, 1), trend_state="stable", trend_pct=0.0)
        _make_usage_snapshot(db, tl_org, "utrend@acme.com", date(2026, 7, 2), trend_state="declining", trend_pct=-33.0)

        resp = client.get(
            "/api/v1/customers/utrend@acme.com/timeline?limit=50",
            headers=tl_headers,
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        types = {e["type"] for e in events}
        assert "usage_trend_change" in types

        ev = next(e for e in events if e["type"] == "usage_trend_change")
        assert ev["old_trend_state"] == "stable"
        assert ev["new_trend_state"] == "declining"
        assert ev["usage_trend_pct"] == -33.0
        assert isinstance(ev["description"], str) and ev["description"]

    def test_usage_trend_change_null_pair_produces_no_event(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        """AC4 at the endpoint level — pre-existing NULL rows never fabricate
        an event visible over the wire."""
        _make_health(db, tl_org, "utrendnull@acme.com")
        _make_usage_snapshot(db, tl_org, "utrendnull@acme.com", date(2026, 7, 1), trend_state=None, trend_pct=None)
        _make_usage_snapshot(db, tl_org, "utrendnull@acme.com", date(2026, 7, 2), trend_state=None, trend_pct=None)

        resp = client.get(
            "/api/v1/customers/utrendnull@acme.com/timeline?limit=50",
            headers=tl_headers,
        )
        assert resp.status_code == 200
        types = {e["type"] for e in resp.json()["events"]}
        assert "usage_trend_change" not in types

    def test_usage_trend_change_appears_on_public_timeline_same_shape(
        self, client: TestClient, tl_org: Organization, db: Session
    ):
        """AC7 — present on both the internal /timeline and the public
        /api/public/v1/customers/{email}/timeline, with the same shape."""
        email = "utrendpublic@acme.com"
        _make_health(db, tl_org, email)
        _make_usage_snapshot(db, tl_org, email, date(2026, 7, 1), trend_state="declining", trend_pct=-31.0)
        _make_usage_snapshot(db, tl_org, email, date(2026, 7, 2), trend_state="stable", trend_pct=0.0)

        raw_key = _make_api_key(db, tl_org.id, scopes="read")
        resp = client.get(
            f"/api/public/v1/customers/{email}/timeline?limit=50",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        types = {e["type"] for e in events}
        assert "usage_trend_change" in types

        ev = next(e for e in events if e["type"] == "usage_trend_change")
        assert ev["old_trend_state"] == "declining"
        assert ev["new_trend_state"] == "stable"
        assert ev["usage_trend_pct"] == 0.0
        assert "description" in ev and "timestamp" in ev and "type" in ev

    def test_usage_trend_change_cross_org_isolation(
        self, client: TestClient, tl_org: Organization, tl_headers: dict, db: Session
    ):
        """AC6 — another org's snapshots never appear."""
        other_org = Organization(name="Other Trend Org", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        email = "utrendisolated@acme.com"
        _make_health(db, tl_org, email)
        _make_usage_snapshot(db, other_org, email, date(2026, 7, 1), trend_state="stable", trend_pct=0.0)
        _make_usage_snapshot(db, other_org, email, date(2026, 7, 2), trend_state="declining", trend_pct=-31.0)

        resp = client.get(
            f"/api/v1/customers/{email}/timeline?limit=50",
            headers=tl_headers,
        )
        assert resp.status_code == 200
        types = {e["type"] for e in resp.json()["events"]}
        assert "usage_trend_change" not in types
