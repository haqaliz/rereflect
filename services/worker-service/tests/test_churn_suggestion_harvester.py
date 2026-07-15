"""
TDD tests for churn_suggestion_harvester.harvest_org_suggestions
(harvester-core aspect).

Strategy (mirrors test_hubspot_sync.py:29-66): file-local in-memory SQLite
engine (not conftest's) + a hand-written Fake client class — no MagicMock,
no `patch` (AC 9 forbids it in this aspect's tests).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models import Base, ChurnLabelSuggestion, CustomerChurnEvent
from src.services.churn_suggestion_harvester import harvest_org_suggestions

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
# Hand-written Fake client (no MagicMock, no patch)
# ---------------------------------------------------------------------------


class FakeCrmClient:
    def __init__(self, deals_by_company=None, opps_by_account=None, raises=False):
        self.deals_by_company = deals_by_company or {}
        self.opps_by_account = opps_by_account or {}
        self.raises = raises
        self.deal_calls: list[str] = []
        self.opp_calls: list[str] = []

    def get_closed_lost_deals_for_company(self, company_id):
        if self.raises:
            raise RuntimeError("boom: hubspot fetch failed")
        self.deal_calls.append(company_id)
        return self.deals_by_company.get(company_id, [])

    def get_lost_opportunities(self, account_id):
        if self.raises:
            raise RuntimeError("boom: salesforce fetch failed")
        self.opp_calls.append(account_id)
        return self.opps_by_account.get(account_id, [])


def _hs_deal(deal_id: str, pipeline: str = "renewal") -> dict:
    return {
        "id": deal_id,
        "properties": {
            "dealname": f"Deal {deal_id}",
            "dealstage": "closedlost",
            "amount": "1000",
            "closedate": "2026-06-15T00:00:00Z",
            "pipeline": pipeline,
        },
    }


def _existing_suggestion(
    db: Session,
    org_id: int,
    email: str,
    ext_id: str,
    provider: str = "hubspot",
    status: str = "pending",
) -> ChurnLabelSuggestion:
    row = ChurnLabelSuggestion(
        organization_id=org_id,
        customer_email=email,
        provider=provider,
        external_opportunity_id=ext_id,
        suggested_churned_at=datetime(2026, 1, 1),
        evidence={},
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _churn_event(
    db: Session, org_id: int, email: str, recovered_at=None
) -> CustomerChurnEvent:
    ev = CustomerChurnEvent(
        organization_id=org_id,
        customer_email=email,
        churned_at=datetime(2026, 1, 1),
        reason_code="other",
        source="manual",
        recovered_at=recovered_at,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


RENEWAL_SET = frozenset({"renewal"})
KNOWN_EMAILS = frozenset({"alice@example.com"})


class TestHappyPathIdempotency:
    def test_n_candidates_insert_n_pending_rows(self, db):
        client = FakeCrmClient(
            deals_by_company={"co1": [_hs_deal("d1"), _hs_deal("d2"), _hs_deal("d3")]}
        )

        result = harvest_org_suggestions(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert result["scanned"] == 3
        assert result["suggested"] == 3
        rows = db.query(ChurnLabelSuggestion).all()
        assert len(rows) == 3
        assert all(r.status == "pending" for r in rows)

    def test_second_run_inserts_zero_rows_unchanged(self, db):
        client = FakeCrmClient(
            deals_by_company={"co1": [_hs_deal("d1"), _hs_deal("d2"), _hs_deal("d3")]}
        )
        kwargs = dict(
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        harvest_org_suggestions(1, db, client, **kwargs)
        first_ids = sorted(r.id for r in db.query(ChurnLabelSuggestion).all())

        second_client = FakeCrmClient(
            deals_by_company={"co1": [_hs_deal("d1"), _hs_deal("d2"), _hs_deal("d3")]}
        )
        result = harvest_org_suggestions(1, db, second_client, **kwargs)

        assert result["scanned"] == 3
        assert result["suggested"] == 0
        assert result["skipped_existing"] == 3
        second_ids = sorted(r.id for r in db.query(ChurnLabelSuggestion).all())
        assert second_ids == first_ids

    def test_memoizes_per_company_fetch(self, db):
        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1")]})

        harvest_org_suggestions(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=frozenset({"alice@example.com", "bob@example.com"}),
            company_ids={"alice@example.com": "co1", "bob@example.com": "co1"},
        )

        assert client.deal_calls == ["co1"]


class TestSuppression:
    def test_rejected_suggestion_not_re_suggested(self, db):
        _existing_suggestion(db, 1, "alice@example.com", "d1", status="rejected")
        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1")]})

        result = harvest_org_suggestions(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert result["suggested"] == 0
        assert result["skipped_existing"] == 1
        row = db.query(ChurnLabelSuggestion).filter_by(external_opportunity_id="d1").one()
        assert row.status == "rejected"

    def test_confirmed_suggestion_not_duplicated(self, db):
        _existing_suggestion(db, 1, "alice@example.com", "d1", status="confirmed")
        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1")]})

        harvest_org_suggestions(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        rows = db.query(ChurnLabelSuggestion).filter_by(external_opportunity_id="d1").all()
        assert len(rows) == 1
        assert rows[0].status == "confirmed"

    def test_active_churn_event_customer_is_skipped(self, db):
        _churn_event(db, 1, "alice@example.com", recovered_at=None)
        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d-new")]})

        result = harvest_org_suggestions(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert result["suggested"] == 0
        assert result["skipped_existing"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_recovered_churn_event_customer_is_not_skipped(self, db):
        _churn_event(db, 1, "alice@example.com", recovered_at=datetime(2026, 2, 1))
        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d-new")]})

        result = harvest_org_suggestions(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        assert result["suggested"] == 1
        assert db.query(ChurnLabelSuggestion).count() == 1


class TestCapAndErrors:
    def test_cap_drops_remainder_and_logs_warning(self, db, caplog):
        deals = [_hs_deal(f"d{i}") for i in range(250)]
        client = FakeCrmClient(deals_by_company={"co1": deals})

        with caplog.at_level(logging.WARNING):
            result = harvest_org_suggestions(
                1, db, client,
                provider="hubspot",
                renewal_set=RENEWAL_SET,
                known_emails=KNOWN_EMAILS,
                company_ids={"alice@example.com": "co1"},
                cap=200,
            )

        assert result["suggested"] == 200
        assert result["dropped_by_cap"] == 50
        assert db.query(ChurnLabelSuggestion).count() == 200

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, "expected a WARNING log for the cap"
        message = warning_records[0].getMessage()
        assert "1" in message
        assert "hubspot" in message
        assert "200" in message
        assert "50" in message

    def test_customer_churn_events_count_unchanged_on_happy_path(self, db):
        _churn_event(db, 99, "someone-else@example.com", recovered_at=datetime(2026, 1, 5))
        before = db.query(CustomerChurnEvent).count()

        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1"), _hs_deal("d2")]})
        harvest_org_suggestions(
            1, db, client,
            provider="hubspot",
            renewal_set=RENEWAL_SET,
            known_emails=KNOWN_EMAILS,
            company_ids={"alice@example.com": "co1"},
        )

        after = db.query(CustomerChurnEvent).count()
        assert before == after

    def test_raising_client_returns_error_status_and_logs(self, db, caplog):
        client = FakeCrmClient(deals_by_company={"co1": [_hs_deal("d1")]}, raises=True)

        with caplog.at_level(logging.ERROR):
            result = harvest_org_suggestions(
                1, db, client,
                provider="hubspot",
                renewal_set=RENEWAL_SET,
                known_emails=KNOWN_EMAILS,
                company_ids={"alice@example.com": "co1"},
            )

        assert result["status"] == "error"
        assert db.query(ChurnLabelSuggestion).count() == 0
        assert any(r.levelno >= logging.ERROR for r in caplog.records)
