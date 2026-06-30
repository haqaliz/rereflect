"""
TDD tests for customer profile, history, feedbacks, and activity endpoints.
Tests:
  GET /api/v1/customers/{email}         - Customer profile
  GET /api/v1/customers/{email}/history - Health score history
  GET /api/v1/customers/{email}/feedbacks - Recent feedbacks (last 15)
  GET /api/v1/customers/{email}/activity  - Recent activity (last 10 events)
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.customer_health import CustomerHealth
from src.models.customer_health_history import CustomerHealthHistory
from src.models.crm_enrichment import CrmEnrichment
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Profile Test Company", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_org: Organization) -> User:
    user = User(
        email="prouser@example.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_headers(pro_user: User) -> dict:
    token = create_access_token({
        "user_id": pro_user.id,
        "organization_id": pro_user.organization_id,
        "role": pro_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Test Company", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_org: Organization) -> User:
    user = User(
        email="freeuser@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_headers(free_user: User) -> dict:
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def make_health(db, org, email, **kwargs) -> CustomerHealth:
    defaults = dict(
        health_score=60,
        risk_level="moderate",
        feedback_count=5,
        confidence_level="medium",
        churn_risk_component=50,
        sentiment_component=60,
        resolution_component=70,
        frequency_component=55,
        last_feedback_at=datetime.utcnow(),
        is_archived=False,
    )
    defaults.update(kwargs)
    h = CustomerHealth(organization_id=org.id, customer_email=email, **defaults)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def make_feedback(db, org, email, text="test", workflow_status="new", sentiment_label="neutral",
                  sentiment_score=0.0, churn_risk_score=30, source="email", created_at=None) -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org.id,
        customer_email=email,
        text=text,
        source=source,
        workflow_status=workflow_status,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        churn_risk_score=churn_risk_score,
        is_urgent=False,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def make_workflow_event(db, org, feedback_id, event_type="status_changed",
                        old_value="new", new_value="resolved", created_at=None) -> FeedbackWorkflowEvent:
    ev = FeedbackWorkflowEvent(
        feedback_id=feedback_id,
        organization_id=org.id,
        event_type=event_type,
        old_value=old_value,
        new_value=new_value,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


# ---------------------------------------------------------------------------
# Profile Endpoint: GET /api/v1/customers/{email}
# ---------------------------------------------------------------------------

class TestCustomerProfile:

    def test_get_profile_returns_200(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "john@acme.com", health_score=75, risk_level="healthy")
        response = client.get("/api/v1/customers/john@acme.com", headers=pro_headers)
        assert response.status_code == 200

    def test_get_profile_has_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "fields@acme.com", health_score=50, risk_level="moderate",
                   customer_name="Fields Test")
        response = client.get("/api/v1/customers/fields@acme.com", headers=pro_headers)
        data = response.json()
        assert data["customer_email"] == "fields@acme.com"
        assert data["customer_name"] == "Fields Test"
        assert data["health_score"] == 50
        assert data["risk_level"] == "moderate"
        assert "confidence_level" in data
        assert "feedback_count" in data
        assert "churn_risk_component" in data
        assert "sentiment_component" in data
        assert "resolution_component" in data
        assert "frequency_component" in data
        assert "is_archived" in data
        assert "created_at" in data

    def test_get_profile_not_found_returns_404(self, client: TestClient, pro_headers: dict):
        response = client.get("/api/v1/customers/nonexistent@example.com", headers=pro_headers)
        assert response.status_code == 404

    def test_get_profile_wrong_org_returns_404(self, client: TestClient, pro_org: Organization, free_org: Organization,
                                               pro_headers: dict, free_headers: dict, db: Session):
        """Customer in org A should not be visible to org B."""
        make_health(db, pro_org, "secret@acme.com")
        response = client.get("/api/v1/customers/secret@acme.com", headers=free_headers)
        assert response.status_code in (403, 404)  # Either forbidden (plan gate) or not found

    def test_free_plan_returns_403(self, client: TestClient, free_headers: dict):
        response = client.get("/api/v1/customers/anyone@example.com", headers=free_headers)
        assert response.status_code == 403

    def test_get_profile_shows_llm_analysis(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        analyzed_at = datetime.utcnow() - timedelta(hours=2)
        make_health(db, pro_org, "llm@acme.com", llm_analysis="Customer is at risk of churning",
                   llm_analyzed_at=analyzed_at)
        response = client.get("/api/v1/customers/llm@acme.com", headers=pro_headers)
        data = response.json()
        assert data["llm_analysis"] == "Customer is at risk of churning"
        assert data["llm_analyzed_at"] is not None

    def test_profile_includes_usage_component_when_set(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        """usage_component stored on the health row must be surfaced on the profile response."""
        make_health(db, pro_org, "usage_set@acme.com", usage_component=72)
        response = client.get("/api/v1/customers/usage_set@acme.com", headers=pro_headers)
        assert response.status_code == 200
        data = response.json()
        assert "usage_component" in data, "usage_component field must be present in profile response"
        assert data["usage_component"] == 72

    def test_profile_usage_component_is_none_when_null(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        """When usage_component column is NULL (legacy row), the field must be None/null — not fabricated."""
        make_health(db, pro_org, "usage_null@acme.com")  # no usage_component → NULL
        response = client.get("/api/v1/customers/usage_null@acme.com", headers=pro_headers)
        assert response.status_code == 200
        data = response.json()
        assert "usage_component" in data, "usage_component field must be present even when NULL"
        assert data["usage_component"] is None

    def test_profile_includes_crm_fields_when_row_exists(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        """B2-RED: v1 profile returns all 7 crm_* fields when a CrmEnrichment row exists."""
        import datetime as dt
        make_health(db, pro_org, "crmdata@acme.com")
        db.add(CrmEnrichment(
            organization_id=pro_org.id,
            customer_email="crmdata@acme.com",
            company_name="HubSpot Co",
            lifecycle_stage="customer",
            arr=50000.0,
            renewal_date=dt.datetime(2026, 12, 31),
            deal_name="Renewal Deal",
            deal_stage="negotiation",
            deal_amount=25000.0,
            last_synced_at=dt.datetime(2026, 6, 30, 10, 0, 0),
        ))
        db.commit()

        response = client.get("/api/v1/customers/crmdata@acme.com", headers=pro_headers)
        assert response.status_code == 200
        data = response.json()

        assert data["crm_company_name"] == "HubSpot Co"
        assert data["crm_lifecycle_stage"] == "customer"
        assert abs(data["crm_arr"] - 50000.0) < 0.01
        assert data["crm_renewal_date"] is not None
        assert data["crm_deal_name"] == "Renewal Deal"
        assert data["crm_deal_stage"] == "negotiation"
        assert abs(data["crm_deal_amount"] - 25000.0) < 0.01

    def test_profile_crm_fields_none_when_no_row(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        """B2-RED: v1 profile returns None for all 7 crm_* fields when no CrmEnrichment row."""
        make_health(db, pro_org, "nocrm2@acme.com")

        response = client.get("/api/v1/customers/nocrm2@acme.com", headers=pro_headers)
        assert response.status_code == 200
        data = response.json()

        for field in ["crm_company_name", "crm_lifecycle_stage", "crm_arr",
                      "crm_renewal_date", "crm_deal_name", "crm_deal_stage", "crm_deal_amount"]:
            assert data.get(field) is None, f"Expected {field} to be null"

    def test_serializer_crm_read_uses_savepoint(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        """
        _read_crm_fields must use db.begin_nested() (SAVEPOINT) so a missing
        crm_enrichment table cannot abort the outer SQLAlchemy transaction and
        cause PendingRollbackError on subsequent queries.

        Mirrors TestCrmComponentSavepointIsolation.test_real_missing_table_savepoint_path
        in test_health_crm_component.py.

        RED: begin_nested is never called with bare try/except → spy.call_count == 0
             → assertion fails.
        GREEN: _read_crm_fields wraps the query in db.begin_nested() → call_count >= 1
               → session usable after the rolled-back SAVEPOINT.
        """
        from unittest.mock import patch
        from sqlalchemy import text as sql_text
        from src.services.customer_profile_serializer import _read_crm_fields

        make_health(db, pro_org, "savepoint_crm@acme.com")
        record = db.query(
            __import__("src.models.customer_health", fromlist=["CustomerHealth"]).CustomerHealth
        ).filter_by(customer_email="savepoint_crm@acme.com").first()

        # Spy on begin_nested to verify SAVEPOINT is used.
        with patch.object(db, "begin_nested", wraps=db.begin_nested) as spy:
            result = _read_crm_fields(record, db)

        assert spy.call_count >= 1, (
            "begin_nested must be called to SAVEPOINT-isolate the CRM read. "
            "Without it, a PostgreSQL OperationalError aborts the transaction "
            "and the next db.query() raises PendingRollbackError (HTTP 500)."
        )
        # All crm fields must be None (no CrmEnrichment row exists for this email).
        for field in ["crm_company_name", "crm_lifecycle_stage", "crm_arr",
                      "crm_renewal_date", "crm_deal_name", "crm_deal_stage", "crm_deal_amount"]:
            assert result.get(field) is None, f"Expected {field} to be null when no CRM row"

        # Session must still be usable after _read_crm_fields returned.
        val = db.execute(sql_text("SELECT 1")).scalar()
        assert val == 1, "Session must remain usable after SAVEPOINT-isolated CRM read"


# ---------------------------------------------------------------------------
# History Endpoint: GET /api/v1/customers/{email}/history
# ---------------------------------------------------------------------------

class TestCustomerHistory:

    def test_history_returns_200(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "hist@acme.com")
        response = client.get("/api/v1/customers/hist@acme.com/history", headers=pro_headers)
        assert response.status_code == 200

    def test_history_has_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        response = client.get("/api/v1/customers/newcust@acme.com/history", headers=pro_headers)
        data = response.json()
        assert "history" in data
        assert "period_start" in data
        assert "period_end" in data

    def test_history_empty_when_no_records(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "nohist@acme.com")
        response = client.get("/api/v1/customers/nohist@acme.com/history", headers=pro_headers)
        data = response.json()
        assert data["history"] == []

    def test_history_returns_records_in_range(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        now = datetime.utcnow()
        health = make_health(db, pro_org, "hist2@acme.com")

        # Within 30 days
        in_range = CustomerHealthHistory(
            customer_health_id=health.id,
            organization_id=pro_org.id,
            health_score=60,
            risk_level="moderate",
            recorded_at=now - timedelta(days=15),
        )
        # Outside 30 days
        out_of_range = CustomerHealthHistory(
            customer_health_id=health.id,
            organization_id=pro_org.id,
            health_score=70,
            risk_level="healthy",
            recorded_at=now - timedelta(days=45),
        )
        db.add_all([in_range, out_of_range])
        db.commit()

        response = client.get("/api/v1/customers/hist2@acme.com/history?days=30", headers=pro_headers)
        data = response.json()
        assert len(data["history"]) == 1
        assert data["history"][0]["health_score"] == 60

    def test_history_60_day_range(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        now = datetime.utcnow()
        health = make_health(db, pro_org, "hist3@acme.com")

        record_50d = CustomerHealthHistory(
            customer_health_id=health.id,
            organization_id=pro_org.id,
            health_score=55,
            risk_level="moderate",
            recorded_at=now - timedelta(days=50),
        )
        db.add(record_50d)
        db.commit()

        response = client.get("/api/v1/customers/hist3@acme.com/history?days=60", headers=pro_headers)
        data = response.json()
        assert len(data["history"]) == 1

    def test_history_invalid_days_rejected(self, client: TestClient, pro_headers: dict):
        response = client.get("/api/v1/customers/anyone@example.com/history?days=45", headers=pro_headers)
        assert response.status_code == 422

    def test_history_item_has_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        health = make_health(db, pro_org, "histfields@acme.com")
        hist = CustomerHealthHistory(
            customer_health_id=health.id,
            organization_id=pro_org.id,
            health_score=65,
            churn_risk_component=40,
            sentiment_component=70,
            resolution_component=80,
            frequency_component=60,
            risk_level="moderate",
            recorded_at=datetime.utcnow() - timedelta(days=5),
        )
        db.add(hist)
        db.commit()

        response = client.get("/api/v1/customers/histfields@acme.com/history", headers=pro_headers)
        item = response.json()["history"][0]
        assert "health_score" in item
        assert "churn_risk_component" in item
        assert "sentiment_component" in item
        assert "resolution_component" in item
        assert "frequency_component" in item
        assert "risk_level" in item
        assert "recorded_at" in item

    def test_history_free_plan_returns_403(self, client: TestClient, free_headers: dict):
        response = client.get("/api/v1/customers/anyone@example.com/history", headers=free_headers)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Feedbacks Endpoint: GET /api/v1/customers/{email}/feedbacks
# ---------------------------------------------------------------------------

class TestCustomerFeedbacks:

    def test_feedbacks_returns_200(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "fb@acme.com")
        response = client.get("/api/v1/customers/fb@acme.com/feedbacks", headers=pro_headers)
        assert response.status_code == 200

    def test_feedbacks_has_required_structure(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "fb2@acme.com")
        response = client.get("/api/v1/customers/fb2@acme.com/feedbacks", headers=pro_headers)
        data = response.json()
        assert "feedbacks" in data
        assert "total_count" in data
        assert "view_all_url" in data

    def test_feedbacks_returns_max_15(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "many@acme.com")
        for i in range(20):
            make_feedback(db, pro_org, "many@acme.com", text=f"Feedback {i}")
        response = client.get("/api/v1/customers/many@acme.com/feedbacks", headers=pro_headers)
        data = response.json()
        assert len(data["feedbacks"]) == 15
        assert data["total_count"] == 20

    def test_feedbacks_item_has_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "fbfields@acme.com")
        make_feedback(db, pro_org, "fbfields@acme.com", text="The billing page keeps crashing",
                     workflow_status="in_review", sentiment_label="negative",
                     sentiment_score=-0.72, churn_risk_score=68, source="slack")
        response = client.get("/api/v1/customers/fbfields@acme.com/feedbacks", headers=pro_headers)
        item = response.json()["feedbacks"][0]
        assert "id" in item
        assert "text_snippet" in item
        assert "sentiment_label" in item
        assert "sentiment_score" in item
        assert "churn_risk_score" in item
        assert "workflow_status" in item
        assert "created_at" in item
        assert "source" in item

    def test_feedbacks_text_snippet_truncated(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        long_text = "A" * 200
        make_health(db, pro_org, "trunc@acme.com")
        make_feedback(db, pro_org, "trunc@acme.com", text=long_text)
        response = client.get("/api/v1/customers/trunc@acme.com/feedbacks", headers=pro_headers)
        item = response.json()["feedbacks"][0]
        assert len(item["text_snippet"]) <= 103  # 100 chars + "..."

    def test_feedbacks_view_all_url_contains_email(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "viewall@acme.com")
        response = client.get("/api/v1/customers/viewall@acme.com/feedbacks", headers=pro_headers)
        url = response.json()["view_all_url"]
        assert "viewall@acme.com" in url

    def test_feedbacks_org_isolation(self, client: TestClient, pro_org: Organization, free_org: Organization,
                                     pro_headers: dict, db: Session):
        """Should not return feedbacks from other orgs."""
        make_health(db, pro_org, "isolated@acme.com")
        # Feedback in wrong org
        make_feedback(db, free_org, "isolated@acme.com", text="Wrong org feedback")
        response = client.get("/api/v1/customers/isolated@acme.com/feedbacks", headers=pro_headers)
        data = response.json()
        assert len(data["feedbacks"]) == 0

    def test_feedbacks_free_plan_returns_403(self, client: TestClient, free_headers: dict):
        response = client.get("/api/v1/customers/anyone@example.com/feedbacks", headers=free_headers)
        assert response.status_code == 403

    def test_feedbacks_ordered_by_most_recent_first(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        now = datetime.utcnow()
        make_health(db, pro_org, "order@acme.com")
        make_feedback(db, pro_org, "order@acme.com", text="Old feedback", created_at=now - timedelta(days=5))
        make_feedback(db, pro_org, "order@acme.com", text="New feedback", created_at=now - timedelta(hours=1))
        response = client.get("/api/v1/customers/order@acme.com/feedbacks", headers=pro_headers)
        items = response.json()["feedbacks"]
        assert items[0]["text_snippet"].startswith("New")


# ---------------------------------------------------------------------------
# Activity Endpoint: GET /api/v1/customers/{email}/activity
# ---------------------------------------------------------------------------

class TestCustomerActivity:

    def test_activity_returns_200(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "act@acme.com")
        response = client.get("/api/v1/customers/act@acme.com/activity", headers=pro_headers)
        assert response.status_code == 200

    def test_activity_has_events_field(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "actfield@acme.com")
        response = client.get("/api/v1/customers/actfield@acme.com/activity", headers=pro_headers)
        data = response.json()
        assert "events" in data

    def test_activity_includes_feedback_created(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "fbcreated@acme.com")
        make_feedback(db, pro_org, "fbcreated@acme.com", text="New feedback")
        response = client.get("/api/v1/customers/fbcreated@acme.com/activity", headers=pro_headers)
        events = response.json()["events"]
        types = [e["type"] for e in events]
        assert "feedback_created" in types

    def test_activity_includes_status_changed(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "statuschange@acme.com")
        fb = make_feedback(db, pro_org, "statuschange@acme.com")
        make_workflow_event(db, pro_org, fb.id, new_value="resolved")
        response = client.get("/api/v1/customers/statuschange@acme.com/activity", headers=pro_headers)
        events = response.json()["events"]
        types = [e["type"] for e in events]
        assert "status_changed" in types

    def test_activity_includes_health_score_changed(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        health = make_health(db, pro_org, "scorechange@acme.com")
        hist = CustomerHealthHistory(
            customer_health_id=health.id,
            organization_id=pro_org.id,
            health_score=45,
            risk_level="at_risk",
            recorded_at=datetime.utcnow() - timedelta(days=2),
        )
        db.add(hist)
        db.commit()
        response = client.get("/api/v1/customers/scorechange@acme.com/activity", headers=pro_headers)
        events = response.json()["events"]
        types = [e["type"] for e in events]
        assert "health_score_changed" in types

    def test_activity_returns_max_10_events(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "maxevents@acme.com")
        for i in range(15):
            make_feedback(db, pro_org, "maxevents@acme.com", text=f"FB {i}",
                         created_at=datetime.utcnow() - timedelta(hours=i))
        response = client.get("/api/v1/customers/maxevents@acme.com/activity", headers=pro_headers)
        events = response.json()["events"]
        assert len(events) <= 10

    def test_activity_events_have_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_health(db, pro_org, "evfields@acme.com")
        make_feedback(db, pro_org, "evfields@acme.com")
        response = client.get("/api/v1/customers/evfields@acme.com/activity", headers=pro_headers)
        event = response.json()["events"][0]
        assert "type" in event
        assert "description" in event
        assert "timestamp" in event

    def test_activity_events_ordered_by_timestamp_desc(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        now = datetime.utcnow()
        make_health(db, pro_org, "evorder@acme.com")
        make_feedback(db, pro_org, "evorder@acme.com", text="Old", created_at=now - timedelta(days=3))
        make_feedback(db, pro_org, "evorder@acme.com", text="New", created_at=now - timedelta(hours=1))
        response = client.get("/api/v1/customers/evorder@acme.com/activity", headers=pro_headers)
        events = response.json()["events"]
        # Events should be most recent first
        if len(events) >= 2:
            from datetime import datetime as dt
            ts0 = dt.fromisoformat(events[0]["timestamp"].replace("Z", "+00:00").replace("+00:00", ""))
            ts1 = dt.fromisoformat(events[1]["timestamp"].replace("Z", "+00:00").replace("+00:00", ""))
            assert ts0 >= ts1

    def test_activity_free_plan_returns_403(self, client: TestClient, free_headers: dict):
        response = client.get("/api/v1/customers/anyone@example.com/activity", headers=free_headers)
        assert response.status_code == 403
