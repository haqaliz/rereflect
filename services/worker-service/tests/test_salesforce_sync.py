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


def _make_mock_client(
    contacts=None, account=None, opportunities=None, lost_opportunities=None
) -> MagicMock:
    mc = MagicMock()
    mc.list_contacts.return_value = contacts or []
    mc.get_account.return_value = account
    mc.get_open_opportunities.return_value = opportunities or []
    mc.get_lost_opportunities.return_value = lost_opportunities or []
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
# TestSalesforceContactIdPersistence (push-task-trigger Phase 1)
# ---------------------------------------------------------------------------


class TestSalesforceContactIdPersistence:
    def test_salesforce_contact_id_persisted_after_match(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[
                {"Id": "003c1AAAA", "Email": "alice@example.com", "AccountId": None}
            ],
        )

        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.salesforce_contact_id == "003c1AAAA"

    def test_duplicate_email_picks_lowest_id_deterministically(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        # Two Contacts share the same email; "003c1AAAA" < "003c2BBBB"
        # lexicographically — the lower Id must win deterministically.
        client = _make_mock_client(
            contacts=[
                {"Id": "003c2BBBB", "Email": "alice@example.com", "AccountId": None},
                {"Id": "003c1AAAA", "Email": "alice@example.com", "AccountId": None},
            ],
        )

        result, _ = _run_sync_org(org.id, db, client)

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1
        assert rows[0].salesforce_contact_id == "003c1AAAA"
        assert result["contacts_matched"] == 1


# ---------------------------------------------------------------------------
# TestSyncOrgAccountMemoization (M2)
# ---------------------------------------------------------------------------


class TestSyncOrgAccountMemoization:
    def test_shared_account_fetched_once_across_matched_contacts(self, db):
        """M2: two matched contacts sharing one AccountId must trigger only
        ONE get_account/get_open_opportunities call per sync run, not one
        per contact (N+1)."""
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        _make_customer(db, org.id, "bob@example.com")

        client = _make_mock_client(
            contacts=[
                {"Id": "003c1", "Email": "alice@example.com", "AccountId": "001a1"},
                {"Id": "003c2", "Email": "bob@example.com", "AccountId": "001a1"},
            ],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 50000, "Type": "Customer"},
            opportunities=[
                {"Name": "Acme Renewal", "StageName": "Negotiation", "Amount": 1000, "CloseDate": "2026-01-01", "IsClosed": False},
            ],
        )

        result, _ = _run_sync_org(org.id, db, client)

        assert result["contacts_matched"] == 2
        assert client.get_account.call_count == 1
        assert client.get_open_opportunities.call_count == 1

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 2
        for row in rows:
            assert row.company_name == "Acme"
            assert row.deal_name == "Acme Renewal"


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


# ---------------------------------------------------------------------------
# TestFanOutTask
# ---------------------------------------------------------------------------


class TestFanOutTask:
    def test_fanout_enqueues_active_integrations_only(self, db):
        active = SalesforceIntegration(
            organization_id=1,
            refresh_token="enc-token",
            instance_url="https://active.my.salesforce.com",
            is_active=True,
            connected_at=datetime.utcnow(),
            contacts_synced=0,
            contacts_matched=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        inactive = SalesforceIntegration(
            organization_id=2,
            refresh_token="enc-token2",
            instance_url="https://inactive.my.salesforce.com",
            is_active=False,
            connected_at=datetime.utcnow(),
            contacts_synced=0,
            contacts_matched=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(active)
        db.add(inactive)
        db.commit()
        db.refresh(active)

        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        with patch.object(ss, "get_db_session", _fake_db_session), \
             patch.object(ss, "sync_salesforce_org") as mock_task:
            mock_task.delay = MagicMock()
            ss.sync_all_salesforce()

        mock_task.delay.assert_called_once_with(active.id)

    def test_fanout_one_org_raising_does_not_abort_others(self, db):
        integ1 = SalesforceIntegration(
            organization_id=1, refresh_token="t1", instance_url="https://a.my.salesforce.com",
            is_active=True, connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        integ2 = SalesforceIntegration(
            organization_id=2, refresh_token="t2", instance_url="https://b.my.salesforce.com",
            is_active=True, connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        integ3 = SalesforceIntegration(
            organization_id=3, refresh_token="t3", instance_url="https://c.my.salesforce.com",
            is_active=True, connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add_all([integ1, integ2, integ3])
        db.commit()

        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        call_count = 0

        def _side_effect(integration_id):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated failure on second org")

        with patch.object(ss, "get_db_session", _fake_db_session), \
             patch.object(ss, "sync_salesforce_org") as mock_task:
            mock_task.delay = MagicMock(side_effect=_side_effect)
            ss.sync_all_salesforce()

        assert mock_task.delay.call_count == 3

    def test_fanout_no_active_integrations_returns_zero(self, db):
        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        with patch.object(ss, "get_db_session", _fake_db_session), \
             patch.object(ss, "sync_salesforce_org") as mock_task:
            mock_task.delay = MagicMock()
            result = ss.sync_all_salesforce()

        assert result["status"] == "no_integrations"
        assert result["queued"] == 0


# ---------------------------------------------------------------------------
# TestSyncSalesforceOrgBody (missing key / auth error / transient error)
# ---------------------------------------------------------------------------


class TestSyncSalesforceOrgBody:
    def test_sync_salesforce_org_missing_encryption_key(self, db):
        """Task returns error dict without raising when LLM_ENCRYPTION_KEY unset."""
        integ = SalesforceIntegration(
            organization_id=1, refresh_token="enc", instance_url="https://acme.my.salesforce.com",
            is_active=True, connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)

        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        with patch.object(ss, "get_db_session", _fake_db_session), \
             patch.object(ss, "_decrypt", side_effect=ValueError("LLM_ENCRYPTION_KEY is not set")):
            task_self = MagicMock()
            result = ss._sync_salesforce_org_body(task_self, integ.id)

        assert result["status"] == "error"
        assert result["reason"] == "missing_encryption_key"

    def test_sync_salesforce_org_retries_on_transient_error(self, db):
        """Task calls self.retry when SalesforceTransientError raised."""
        from celery.exceptions import Retry

        integ = SalesforceIntegration(
            organization_id=1, refresh_token="enc", instance_url="https://acme.my.salesforce.com",
            is_active=True, connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)

        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        task_self = MagicMock()
        task_self.retry.side_effect = Retry()

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.list_contacts.side_effect = ss.SalesforceTransientError("rate limited")

        with patch.object(ss, "get_db_session", _fake_db_session), \
             patch.object(ss, "_decrypt", return_value="plain-refresh-token"), \
             patch.object(ss, "SalesforceClient", return_value=mock_client_instance):
            with pytest.raises(Retry):
                ss._sync_salesforce_org_body(task_self, integ.id)

        task_self.retry.assert_called_once()

    def test_sync_salesforce_org_invalid_grant_disconnects_no_retry(self, db):
        """invalid_grant on token refresh marks the integration inactive and does NOT retry."""
        integ = SalesforceIntegration(
            organization_id=1, refresh_token="enc", instance_url="https://acme.my.salesforce.com",
            is_active=True, connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)

        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        task_self = MagicMock()

        with patch.object(ss, "get_db_session", _fake_db_session), \
             patch.object(ss, "_decrypt", return_value="plain-refresh-token"), \
             patch.object(ss, "SalesforceClient", side_effect=ss.SalesforceAuthError("invalid_grant")):
            result = ss._sync_salesforce_org_body(task_self, integ.id)

        assert result["status"] == "error"
        assert result["reason"] == "invalid_grant"
        task_self.retry.assert_not_called()

        db.refresh(integ)
        assert integ.is_active is False
        assert integ.last_sync_status == "error"
        assert integ.last_error is not None

    def test_sync_salesforce_org_not_found(self, db):
        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        task_self = MagicMock()
        with patch.object(ss, "get_db_session", _fake_db_session):
            result = ss._sync_salesforce_org_body(task_self, 999999)

        assert result["status"] == "not_found"

    def test_sync_salesforce_org_inactive_skipped(self, db):
        integ = SalesforceIntegration(
            organization_id=1, refresh_token="enc", instance_url="https://acme.my.salesforce.com",
            is_active=False, connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)

        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        task_self = MagicMock()
        with patch.object(ss, "get_db_session", _fake_db_session):
            result = ss._sync_salesforce_org_body(task_self, integ.id)

        assert result["status"] == "inactive"

    def test_sync_salesforce_org_success_updates_stats(self, db):
        _make_customer(db, 1, "alice@example.com")

        integ = SalesforceIntegration(
            organization_id=1, refresh_token="enc", instance_url="https://acme.my.salesforce.com",
            is_active=True, connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)

        import src.tasks.salesforce_sync as ss
        importlib.reload(ss)

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.list_contacts.return_value = [
            {"Id": "003c1", "Email": "alice@example.com", "AccountId": None},
        ]
        mock_client_instance.get_account.return_value = None
        mock_client_instance.get_open_opportunities.return_value = []

        task_self = MagicMock()
        health_mock = MagicMock()
        sys.modules["src.services.health_score_service"] = health_mock

        try:
            with patch.object(ss, "get_db_session", _fake_db_session), \
                 patch.object(ss, "_decrypt", return_value="plain-refresh-token"), \
                 patch.object(ss, "SalesforceClient", return_value=mock_client_instance):
                result = ss._sync_salesforce_org_body(task_self, integ.id)
        finally:
            sys.modules.pop("src.services.health_score_service", None)

        assert result["status"] == "success"
        assert result["contacts_synced"] == 1
        assert result["contacts_matched"] == 1

        db.refresh(integ)
        assert integ.last_sync_status == "success"
        assert integ.last_error is None
        assert integ.contacts_synced == 1
        assert integ.contacts_matched == 1
        assert integ.last_synced_at is not None


# ---------------------------------------------------------------------------
# TestModelsAndMigration (push-task-trigger: SalesforceIntegration parity)
# ---------------------------------------------------------------------------


class TestModelsAndMigration:
    def test_worker_and_backend_salesforce_integration_columns_match(self):
        """Worker SalesforceIntegration mirror columns must exactly match
        backend-api model columns (push-task-trigger aspect: extends the
        crm_enrichment/HubSpotIntegration parity coverage to
        SalesforceIntegration too, now that the writeback task reads/writes
        its writeback_* columns).

        Same sys.path/sys.modules swap technique as
        test_hubspot_sync.py::TestModelsAndMigration.
        """
        import os

        from src.models import SalesforceIntegration as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        worktree = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        backend_src = os.path.join(worktree, "services", "backend-api")

        saved_mods = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
        for k in saved_mods:
            del sys.modules[k]

        sys.path.insert(0, backend_src)
        try:
            from src.models.salesforce_integration import SalesforceIntegration as BackendModel
            backend_cols = {c.name for c in BackendModel.__table__.columns}
        finally:
            sys.path.remove(backend_src)
            for k in list(sys.modules.keys()):
                if k == "src" or k.startswith("src."):
                    del sys.modules[k]
            sys.modules.update(saved_mods)

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )


# ---------------------------------------------------------------------------
# TestCeleryTaskRegistration
# ---------------------------------------------------------------------------


class TestCeleryTaskRegistration:
    def test_sync_all_salesforce_is_registered(self):
        import src.tasks.salesforce_sync  # noqa: F401 — ensure task registration
        from src.celery_app import celery_app
        assert "src.tasks.salesforce_sync.sync_all_salesforce" in celery_app.tasks

    def test_sync_salesforce_org_is_registered(self):
        import src.tasks.salesforce_sync  # noqa: F401 — ensure task registration
        from src.celery_app import celery_app
        assert "src.tasks.salesforce_sync.sync_salesforce_org" in celery_app.tasks

    def test_beat_schedule_has_salesforce_entry(self):
        import src.tasks.salesforce_sync  # noqa: F401 — ensure task registration
        from src.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "sync-salesforce-daily" in schedule
        entry = schedule["sync-salesforce-daily"]
        cron = entry["schedule"]
        assert cron.hour == {3}
        assert cron.minute == {45}  # 03:45 — avoids 03:00 calibration / 03:15 hubspot


# ---------------------------------------------------------------------------
# Phase 1 (provider-churn-fetch): characterization lock — pins the EXISTING
# enrichment output byte-identical before any client edit in this aspect.
# Mirrors TestEnrichmentCharacterizationLock in test_hubspot_sync.py.
# ---------------------------------------------------------------------------


# Fixed payload: 4 opportunities — open/high-amount, open/low, closed-won,
# closed-lost. Amounts are chosen so a broken filter would pick a different
# opportunity than o1.
CHARACTERIZATION_OPPS = [
    {
        "Id": "006o1",
        "Name": "Open High",
        "StageName": "Negotiation",
        "Amount": 900,
        "CloseDate": "2026-09-01",
        "IsClosed": False,
    },
    {
        "Id": "006o2",
        "Name": "Open Low",
        "StageName": "Proposal",
        "Amount": 100,
        "CloseDate": "2026-08-01",
        "IsClosed": False,
    },
    {
        "Id": "006o3",
        "Name": "Won Big",
        "StageName": "Closed Won",
        "Amount": 5000,
        "CloseDate": "2026-05-01",
        "IsClosed": True,
    },
    {
        "Id": "006o4",
        "Name": "Lost Big",
        "StageName": "Closed Lost",
        "Amount": 4000,
        "CloseDate": "2026-01-15",
        "IsClosed": True,
    },
]


class TestEnrichmentCharacterizationLock:
    def test_pick_renewal_opportunity_picks_o1(self):
        from src.tasks.salesforce_sync import _pick_renewal_opportunity

        assert _pick_renewal_opportunity(CHARACTERIZATION_OPPS) is CHARACTERIZATION_OPPS[0]

    def test_pick_renewal_opportunity_ignores_closed(self):
        from src.tasks.salesforce_sync import _pick_renewal_opportunity

        winner = _pick_renewal_opportunity(CHARACTERIZATION_OPPS)
        assert winner["Id"] != "006o3"
        assert winner["Id"] != "006o4"
        # o3/o4 have higher raw amounts (5000, 4000) than the winner (900) —
        # proves the IsClosed exclusion, not just amount ranking.
        assert winner["Amount"] == 900

    def test_enrichment_row_fields_are_exact(self, db):
        from datetime import datetime, timezone
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[
                {"Id": "003c1", "Email": "alice@example.com", "AccountId": "001a1"}
            ],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 5000, "Type": "Customer"},
            opportunities=CHARACTERIZATION_OPPS,
        )

        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        actual = {
            "deal_name": row.deal_name,
            "deal_stage": row.deal_stage,
            "deal_amount": row.deal_amount,
            "renewal_date": row.renewal_date,
        }
        expected = {
            "deal_name": "Open High",
            "deal_stage": "Negotiation",
            "deal_amount": 900.0,
            "renewal_date": datetime(2026, 9, 1),
        }
        assert actual == expected
        assert actual["deal_stage"] not in ("Closed Won", "Closed Lost")


# ---------------------------------------------------------------------------
# Phase 4: churn-suggestion harvest wiring (harvester-core aspect)
# ---------------------------------------------------------------------------


_LOST_RENEWAL_OPP = {
    "Id": "006lost1",
    "Name": "Lost Renewal",
    "StageName": "Closed Lost",
    "Amount": 1000,
    "CloseDate": "2026-06-15",
    "IsClosed": True,
    "IsWon": False,
    "Type": "Renewal",
}


class TestChurnSuggestionHarvestWiring:
    def _make_salesforce_integration(self, db, org_id, *, enabled=False, config=None):
        integ = SalesforceIntegration(
            organization_id=org_id,
            instance_url="https://test.my.salesforce.com",
            refresh_token="enc-refresh",
            connected_at=datetime.utcnow(), is_active=True,
            contacts_synced=0, contacts_matched=0,
            churn_labels_enabled=enabled, churn_label_config=config,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)
        return integ

    def _matched_contact(self):
        return {"Id": "003c1", "Email": "alice@example.com", "AccountId": "001a1"}

    def test_churn_labels_disabled_by_default_yields_zero_rows_and_baseline_result(self, db):
        from src.models import ChurnLabelSuggestion

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        self._make_salesforce_integration(db, org.id)  # churn_labels_enabled defaults False

        client = _make_mock_client(
            contacts=[self._matched_contact()],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 5000, "Type": "Customer"},
            lost_opportunities=[_LOST_RENEWAL_OPP],
        )

        result, _ = _run_sync_org(org.id, db, client)

        assert result == {"contacts_synced": 1, "contacts_matched": 1, "unmatched": 0}
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_churn_labels_enabled_with_matching_config_creates_pending_suggestion(self, db):
        from src.models import ChurnLabelSuggestion

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        self._make_salesforce_integration(
            db, org.id, enabled=True,
            config={"renewal_opportunity_types": ["Renewal"]},
        )

        client = _make_mock_client(
            contacts=[self._matched_contact()],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 5000, "Type": "Customer"},
            lost_opportunities=[_LOST_RENEWAL_OPP],
        )

        result, _ = _run_sync_org(org.id, db, client)

        assert result == {"contacts_synced": 1, "contacts_matched": 1, "unmatched": 0}
        rows = db.query(ChurnLabelSuggestion).all()
        assert len(rows) == 1
        assert rows[0].status == "pending"
        assert rows[0].customer_email == "alice@example.com"
        assert rows[0].provider == "salesforce"
        assert rows[0].external_opportunity_id == "006lost1"

    def test_churn_labels_enabled_but_config_empty_yields_zero_rows(self, db):
        from src.models import ChurnLabelSuggestion

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        self._make_salesforce_integration(db, org.id, enabled=True, config={})

        client = _make_mock_client(
            contacts=[self._matched_contact()],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 5000, "Type": "Customer"},
            lost_opportunities=[_LOST_RENEWAL_OPP],
        )

        _run_sync_org(org.id, db, client)

        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_churn_labels_enabled_but_config_absent_yields_zero_rows(self, db):
        from src.models import ChurnLabelSuggestion

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        self._make_salesforce_integration(db, org.id, enabled=True, config=None)

        client = _make_mock_client(
            contacts=[self._matched_contact()],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 5000, "Type": "Customer"},
            lost_opportunities=[_LOST_RENEWAL_OPP],
        )

        _run_sync_org(org.id, db, client)

        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_raising_lost_opportunities_accessor_leaves_enrichment_and_result_intact(self, db):
        from src.models import ChurnLabelSuggestion

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        self._make_salesforce_integration(
            db, org.id, enabled=True,
            config={"renewal_opportunity_types": ["Renewal"]},
        )

        client = _make_mock_client(
            contacts=[self._matched_contact()],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 5000, "Type": "Customer"},
        )
        client.get_lost_opportunities.side_effect = RuntimeError("boom")

        result, _ = _run_sync_org(org.id, db, client)

        assert result == {"contacts_synced": 1, "contacts_matched": 1, "unmatched": 0}
        assert db.query(ChurnLabelSuggestion).count() == 0

    def test_enrichment_row_unaffected_by_harvest_wiring(self, db):
        """Enrichment characterization holds even when harvest is enabled and firing."""
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        self._make_salesforce_integration(
            db, org.id, enabled=True,
            config={"renewal_opportunity_types": ["Renewal"]},
        )

        client = _make_mock_client(
            contacts=[self._matched_contact()],
            account={"Id": "001a1", "Name": "Acme", "AnnualRevenue": 5000, "Type": "Customer"},
            opportunities=CHARACTERIZATION_OPPS,
            lost_opportunities=[_LOST_RENEWAL_OPP],
        )

        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.deal_name == "Open High"
        assert row.deal_stage == "Negotiation"
        assert row.deal_amount == 900.0
