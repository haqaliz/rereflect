"""
TDD tests for salesforce_sync tasks and _sync_org core.

Strategy: in-memory SQLite, mocked SalesforceClient, NO Celery eager mode.
Mirror test_hubspot_sync.py structure exactly.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# conftest already stubs src.config + src.database before this file imports them
from src.models import Base, CustomerHealth, Organization, SalesforceIntegration

# ---------------------------------------------------------------------------
# In-memory SQLite engine (isolated)
# ---------------------------------------------------------------------------

_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


@contextmanager
def _fake_db_session():
    """Thin context manager yielding a SQLite session — mirrors get_db_session."""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _fresh_db():
    """Create all tables before each test; drop after."""
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture()
def db() -> Session:
    """Return a plain SQLite session for fixture setup."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session) -> Organization:
    org = Organization(name="TestCorp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_customer(db: Session, org_id: int, email: str) -> CustomerHealth:
    ch = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        health_score=50,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _make_mock_client(contacts=None, account=None, opportunities=None) -> MagicMock:
    mc = MagicMock()
    mc.list_contacts.return_value = contacts or []
    mc.get_account.return_value = account
    mc.get_open_opportunities.return_value = opportunities or []
    return mc


def _run_sync_org(org_id: int, db: Session, mock_client, health_mock=None):
    """
    Call _sync_org with:
      - get_db_session patched to use test SQLite DB
      - src.services.health_score_service injected as health_mock
    """
    if health_mock is None:
        health_mock = MagicMock()

    sys.modules["src.services.health_score_service"] = health_mock

    try:
        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        with patch.object(ss, "get_db_session", _fake_db_session):
            result = ss._sync_org(org_id, db, mock_client)

        return result, health_mock
    finally:
        sys.modules.pop("src.services.health_score_service", None)


# ---------------------------------------------------------------------------
# TestSyncOrgUpsert
# ---------------------------------------------------------------------------


class TestSyncOrgUpsert:
    def test_upsert_one_row_per_matched_email(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[
                {"Id": "003c1", "Email": "alice@example.com", "AccountId": "001a1"}
            ],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 50000, "Type": "Customer"},
            opportunities=[],
        )

        _run_sync_org(org.id, db, client)

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1
        assert rows[0].organization_id == org.id
        assert rows[0].customer_email == "alice@example.com"
        assert rows[0].provider == "salesforce"
        assert rows[0].company_name == "Acme"
        assert rows[0].arr == 50000.0
        assert rows[0].lifecycle_stage == "Customer"
        assert rows[0].renewal_date is None

    def test_unmatched_contact_not_upserted(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        # no customers in this org

        client = _make_mock_client(
            contacts=[{"Id": "003c1", "Email": "bob@example.com", "AccountId": None}],
        )

        result, _ = _run_sync_org(org.id, db, client)

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 0
        assert result["contacts_matched"] == 0
        assert result["contacts_synced"] == 1
        assert result["unmatched"] == 1

    def test_email_matching_is_case_insensitive(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "Alice@Example.COM")

        client = _make_mock_client(
            contacts=[{"Id": "003c1", "Email": "alice@example.com", "AccountId": None}],
        )

        _run_sync_org(org.id, db, client)

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1

    def test_cross_tenant_isolation(self, db):
        from src.models import CrmEnrichment

        org1 = _make_org(db)
        org2 = Organization(name="OtherCorp", plan="free")
        db.add(org2)
        db.commit()
        db.refresh(org2)

        _make_customer(db, org1.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[{"Id": "003c1", "Email": "alice@example.com", "AccountId": None}],
        )

        _run_sync_org(org1.id, db, client)

        org1_rows = db.query(CrmEnrichment).filter_by(organization_id=org1.id).all()
        org2_rows = db.query(CrmEnrichment).filter_by(organization_id=org2.id).all()
        assert len(org1_rows) == 1
        assert len(org2_rows) == 0

    def test_no_account_id_skips_account_and_opportunity_calls(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[{"Id": "003c1", "Email": "alice@example.com", "AccountId": None}],
        )

        _run_sync_org(org.id, db, client)

        client.get_account.assert_not_called()
        client.get_open_opportunities.assert_not_called()

        row = db.query(CrmEnrichment).first()
        assert row.company_name is None
        assert row.arr is None


# ---------------------------------------------------------------------------
# TestSyncOrgIdempotency
# ---------------------------------------------------------------------------


class TestSyncOrgIdempotency:
    def test_idempotent_rerun_does_not_duplicate(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[{"Id": "003c1", "Email": "alice@example.com", "AccountId": None}],
        )

        _run_sync_org(org.id, db, client)
        _run_sync_org(org.id, db, client)

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1

    def test_second_run_updates_existing_row(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client1 = _make_mock_client(
            contacts=[
                {"Id": "003c1", "Email": "alice@example.com", "AccountId": "001a1"}
            ],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 10000, "Type": "Customer"},
        )
        _run_sync_org(org.id, db, client1)

        client2 = _make_mock_client(
            contacts=[
                {"Id": "003c1", "Email": "alice@example.com", "AccountId": "001a1"}
            ],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 20000, "Type": "Customer"},
        )
        _run_sync_org(org.id, db, client2)

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1
        assert rows[0].arr == 20000.0


# ---------------------------------------------------------------------------
# TestRenewalOpportunitySelection
# ---------------------------------------------------------------------------


class TestRenewalOpportunitySelection:
    def _setup(self, db, opportunities):
        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        client = _make_mock_client(
            contacts=[
                {"Id": "003c1", "Email": "alice@example.com", "AccountId": "001a1"}
            ],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 5000, "Type": "Customer"},
            opportunities=opportunities,
        )
        return org, client

    def test_renewal_proxy_highest_amount_open_opportunity(self, db):
        from src.models import CrmEnrichment

        opportunities = [
            {
                "Id": "006o1",
                "Name": "Deal One",
                "StageName": "Negotiation",
                "Amount": 5000,
                "CloseDate": "2026-09-01",
                "IsClosed": False,
            },
            {
                "Id": "006o2",
                "Name": "Deal Two",
                "StageName": "Proposal",
                "Amount": 12000,
                "CloseDate": "2026-10-01",
                "IsClosed": False,
            },
        ]
        org, client = self._setup(db, opportunities)
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.deal_amount == 12000.0
        assert row.deal_name == "Deal Two"
        assert row.deal_stage == "Proposal"
        assert row.renewal_date is not None

    def test_renewal_proxy_excludes_closed(self, db):
        from src.models import CrmEnrichment

        opportunities = [
            {
                "Id": "006o1",
                "Name": "Closed Deal",
                "StageName": "Closed Won",
                "Amount": 99999,
                "CloseDate": "2026-09-01",
                "IsClosed": True,
            },
            {
                "Id": "006o2",
                "Name": "Open Deal",
                "StageName": "Proposal",
                "Amount": 1000,
                "CloseDate": "2026-10-01",
                "IsClosed": False,
            },
        ]
        org, client = self._setup(db, opportunities)
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.deal_amount == 1000.0
        assert row.deal_name == "Open Deal"

    def test_no_opportunities_gives_null_renewal(self, db):
        from src.models import CrmEnrichment

        org, client = self._setup(db, opportunities=[])
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.renewal_date is None
        assert row.deal_name is None
        assert row.deal_stage is None
        assert row.deal_amount is None

    def test_opportunity_without_close_date_excluded(self, db):
        from src.models import CrmEnrichment

        opportunities = [
            {
                "Id": "006o1",
                "Name": "No Close Date Deal",
                "StageName": "Proposal",
                "Amount": 99999,
                "CloseDate": None,
                "IsClosed": False,
            },
        ]
        org, client = self._setup(db, opportunities)
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.renewal_date is None


# ---------------------------------------------------------------------------
# TestSyncOrgHealthRecompute
# ---------------------------------------------------------------------------


class TestSyncOrgHealthRecompute:
    def test_update_customer_health_called_once_per_matched_customer(self, db):
        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        _make_customer(db, org.id, "bob@example.com")

        client = _make_mock_client(
            contacts=[
                {"Id": "003c1", "Email": "alice@example.com", "AccountId": None},
                {"Id": "003c2", "Email": "bob@example.com", "AccountId": None},
            ],
        )

        health_mock = MagicMock()
        _run_sync_org(org.id, db, client, health_mock=health_mock)

        assert health_mock.update_customer_health.call_count == 2
        called_emails = {call[0][1] for call in health_mock.update_customer_health.call_args_list}
        assert "alice@example.com" in called_emails
        assert "bob@example.com" in called_emails

    def test_health_import_error_tolerated(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[{"Id": "003c1", "Email": "alice@example.com", "AccountId": None}],
        )

        # Remove the health_score_service from sys.modules to force ImportError path
        sys.modules["src.services.health_score_service"] = None

        try:
            import src.tasks.salesforce_sync as ss
            importlib.reload(ss)
            with patch.object(ss, "get_db_session", _fake_db_session):
                result = ss._sync_org(org.id, db, client)
        finally:
            sys.modules.pop("src.services.health_score_service", None)

        # Should not raise; CrmEnrichment row should still be written
        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1

    def test_unmatched_customer_health_not_called(self, db):
        org = _make_org(db)
        # No customers in org

        client = _make_mock_client(
            contacts=[{"Id": "003c1", "Email": "nobody@example.com", "AccountId": None}],
        )

        health_mock = MagicMock()
        _run_sync_org(org.id, db, client, health_mock=health_mock)

        assert health_mock.update_customer_health.call_count == 0
