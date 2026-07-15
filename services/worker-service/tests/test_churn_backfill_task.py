"""
TDD tests for churn_backfill_task (historical-backfill aspect, Phase 5).

Strategy (mirrors test_churn_backfill.py): file-local in-memory SQLite
engine + hand-written Fake CRM client (no MagicMock for DB/client — the
task's `_backfill_body` is Celery-free and takes `db` + a `client_factory`
directly, so no get_db_session patching is needed at all). A tiny
hand-written FakeTaskSelf stands in for Celery's bound `self` (retry()).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from celery.exceptions import Retry
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.clients.hubspot import HubSpotTransientError
from src.clients.salesforce import SalesforceTransientError
from src.models import (
    Base,
    ChurnLabelSuggestion,
    CustomerChurnEvent,
    CustomerHealth,
    HubSpotIntegration,
    SalesforceIntegration,
)
from src.tasks.churn_backfill_task import _backfill_body

# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated, file-local)
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
# Hand-written fakes (no MagicMock, no patch)
# ---------------------------------------------------------------------------


class FakeTaskSelf:
    """Stand-in for Celery's bound `self` — retry() raises Retry, as real
    Celery does, so the task body's `raise task_self.retry(...)` propagates."""

    def __init__(self):
        self.retry_calls: list[Exception] = []

    def retry(self, exc=None):
        self.retry_calls.append(exc)
        raise Retry(exc=exc)


class FakeHubSpotClient:
    """Context-manager-compatible Fake honoring the same call shape as the
    real HubSpotClient (list_contacts, get_closed_lost_deals_for_company)."""

    def __init__(self, contacts=None, deals_by_company=None, raise_on_fetch=None):
        self.contacts = contacts or []
        self.deals_by_company = deals_by_company or {}
        self.raise_on_fetch = raise_on_fetch
        self.fetch_calls: list[str] = []
        # side effect hook: company_id -> callable(db) invoked before returning
        self.on_fetch_side_effects: dict[str, callable] = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def list_contacts(self):
        return self.contacts

    def get_closed_lost_deals_for_company(self, company_id, *, since=None):
        self.fetch_calls.append(company_id)
        if self.raise_on_fetch:
            raise self.raise_on_fetch
        hook = self.on_fetch_side_effects.get(company_id)
        if hook:
            hook()
        return self.deals_by_company.get(company_id, [])


def _hs_contact(contact_id: str, email: str, company_id: str) -> dict:
    return {
        "id": contact_id,
        "properties": {"email": email, "associatedcompanyid": company_id},
    }


def _hs_deal(deal_id: str, close_date: str, pipeline: str = "renewal") -> dict:
    return {
        "id": deal_id,
        "properties": {
            "dealname": f"Deal {deal_id}",
            "dealstage": "closedlost",
            "amount": "1000",
            "closedate": close_date,
            "pipeline": pipeline,
        },
    }


_NOW = datetime.utcnow()
_INSIDE_WINDOW = (_NOW - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")


def _make_hubspot_integration(
    db: Session,
    org_id: int = 1,
    enabled: bool = True,
    pipeline_ids=("renewal",),
    is_active: bool = True,
    access_token: str = "enc-token",
) -> HubSpotIntegration:
    integ = HubSpotIntegration(
        organization_id=org_id,
        access_token=access_token,
        is_active=is_active,
        churn_labels_enabled=enabled,
        churn_label_config={"renewal_pipeline_ids": list(pipeline_ids)} if pipeline_ids else {},
        connected_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _make_customer(db: Session, org_id: int, email: str) -> CustomerHealth:
    ch = CustomerHealth(organization_id=org_id, customer_email=email, health_score=50)
    db.add(ch)
    db.commit()
    return ch


def _client_factory_for(fake_client):
    def factory(provider, token, integ):
        return fake_client
    return factory


class TestNotFoundAndInactive:
    def test_missing_integration_returns_not_found(self, db):
        task_self = FakeTaskSelf()
        result = _backfill_body(task_self, db, 999, 24, "hubspot")
        assert result == {"status": "not_found", "integration_id": 999}

    def test_inactive_integration_returns_inactive(self, db):
        integ = _make_hubspot_integration(db, is_active=False)
        task_self = FakeTaskSelf()
        result = _backfill_body(task_self, db, integ.id, 24, "hubspot")
        assert result == {"status": "inactive", "integration_id": integ.id}


class TestDefaultDenyRecheck:
    def test_disabled_returns_error_without_building_client(self, db):
        integ = _make_hubspot_integration(db, enabled=False)
        task_self = FakeTaskSelf()

        result = _backfill_body(
            task_self, db, integ.id, 24, "hubspot",
            client_factory=lambda *a: (_ for _ in ()).throw(
                AssertionError("client_factory must not be called")
            ),
        )

        assert result["status"] == "error"
        assert result["reason"] == "churn_labels_disabled_or_unconfigured"
        db.refresh(integ)
        assert integ.backfill_status == "failed"

    def test_empty_renewal_set_returns_error_without_building_client(self, db):
        integ = _make_hubspot_integration(db, enabled=True, pipeline_ids=())
        task_self = FakeTaskSelf()

        result = _backfill_body(
            task_self, db, integ.id, 24, "hubspot",
            client_factory=lambda *a: (_ for _ in ()).throw(
                AssertionError("client_factory must not be called")
            ),
        )

        assert result["status"] == "error"
        assert result["reason"] == "churn_labels_disabled_or_unconfigured"


class TestMissingEncryptionKey:
    def test_missing_key_returns_error_no_retry(self, db):
        def _raise_missing_key(token):
            raise ValueError("LLM_ENCRYPTION_KEY is not set")

        integ = _make_hubspot_integration(db)
        task_self = FakeTaskSelf()

        result = _backfill_body(
            task_self, db, integ.id, 24, "hubspot",
            _decrypt_fn=_raise_missing_key,
        )

        assert result == {"status": "error", "reason": "missing_encryption_key"}
        assert task_self.retry_calls == []
        db.refresh(integ)
        assert integ.backfill_status == "failed"
        assert integ.backfill_error == "missing_encryption_key"


class TestHappyPath:
    def test_completes_and_persists_progress(self, db):
        integ = _make_hubspot_integration(db)
        _make_customer(db, 1, "alice@example.com")

        fake_client = FakeHubSpotClient(
            contacts=[_hs_contact("c1", "alice@example.com", "co1")],
            deals_by_company={"co1": [_hs_deal("d1", _INSIDE_WINDOW)]},
        )
        task_self = FakeTaskSelf()

        result = _backfill_body(
            task_self, db, integ.id, 24, "hubspot",
            client_factory=_client_factory_for(fake_client),
            _decrypt_fn=lambda token: "plaintext-token",
        )

        assert result["status"] == "success"
        assert result["suggested"] == 1
        db.refresh(integ)
        assert integ.backfill_status == "completed"
        assert integ.backfill_progress["suggested"] == 1
        # "since" (the covered window) must be surfaced in progress, not just
        # logged — house rule: no silent caps, dropped count AND window both
        # surfaced to the operator (spec §6).
        assert "since" in integ.backfill_progress
        assert integ.backfill_last_run_at is not None
        assert integ.backfill_error is None
        assert db.query(ChurnLabelSuggestion).count() == 1
        assert db.query(CustomerChurnEvent).count() == 0


class TestTransientRetry:
    def test_transient_error_retries_and_keeps_status_running(self, db):
        integ = _make_hubspot_integration(db)
        _make_customer(db, 1, "alice@example.com")

        fake_client = FakeHubSpotClient(
            contacts=[_hs_contact("c1", "alice@example.com", "co1")],
            raise_on_fetch=HubSpotTransientError("rate limited"),
        )
        task_self = FakeTaskSelf()

        with pytest.raises(Retry):
            _backfill_body(
                task_self, db, integ.id, 24, "hubspot",
                client_factory=_client_factory_for(fake_client),
                _decrypt_fn=lambda token: "plaintext-token",
            )

        assert len(task_self.retry_calls) == 1
        db.refresh(integ)
        assert integ.backfill_status == "running"
        assert integ.backfill_error
        assert db.query(CustomerChurnEvent).count() == 0


class TestCancellationMidRun:
    def test_cancelling_mid_run_stops_before_next_unit_and_persists_partial_progress(
        self, db
    ):
        integ = _make_hubspot_integration(db)
        _make_customer(db, 1, "alice@example.com")
        _make_customer(db, 1, "bob@example.com")

        def _flip_to_cancelling():
            row = (
                db.query(HubSpotIntegration)
                .filter(HubSpotIntegration.id == integ.id)
                .first()
            )
            row.backfill_status = "cancelling"
            db.commit()

        fake_client = FakeHubSpotClient(
            contacts=[
                _hs_contact("c1", "alice@example.com", "co1"),
                _hs_contact("c2", "bob@example.com", "co2"),
            ],
            deals_by_company={
                "co1": [_hs_deal("d1", _INSIDE_WINDOW)],
                "co2": [_hs_deal("d2", _INSIDE_WINDOW)],
            },
        )
        # co1 is processed first (sorted by email: alice < bob) — flip
        # status to "cancelling" as a side effect of fetching co1's deals,
        # simulating a concurrent cancel request landing mid-run.
        fake_client.on_fetch_side_effects["co1"] = _flip_to_cancelling

        task_self = FakeTaskSelf()

        result = _backfill_body(
            task_self, db, integ.id, 24, "hubspot",
            client_factory=_client_factory_for(fake_client),
            _decrypt_fn=lambda token: "plaintext-token",
        )

        assert result["status"] == "cancelled"
        assert fake_client.fetch_calls == ["co1"]  # co2 never fetched
        db.refresh(integ)
        assert integ.backfill_status == "cancelled"
        assert integ.backfill_progress["suggested"] == 1  # co1's suggestion persisted
        assert db.query(ChurnLabelSuggestion).count() == 1
        assert db.query(CustomerChurnEvent).count() == 0


class TestUnknownProvider:
    def test_unknown_provider_returns_error(self, db):
        task_self = FakeTaskSelf()
        result = _backfill_body(task_self, db, 1, 24, "not-a-provider")
        assert result == {"status": "error", "reason": "unknown_provider"}


class TestNoDailyBeatCoupling:
    """AC-1 — this task is distinct from the daily 03:15/03:45 sync beat."""

    def test_backfill_task_not_included_in_beat_schedule(self):
        from src.celery_app import celery_app

        for entry in celery_app.conf.beat_schedule.values():
            assert "churn_backfill_task" not in entry["task"]

    def test_backfill_module_registered_in_include_list_only(self):
        from src.celery_app import celery_app

        assert "src.tasks.churn_backfill_task" in celery_app.conf.include
