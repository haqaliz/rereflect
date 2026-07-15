"""
TDD tests for hubspot_sync tasks and _sync_org core.

Strategy: in-memory SQLite, mocked httpx/client, NO Celery eager mode.
Mirror test_usage_metrics.py structure exactly.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# conftest already stubs src.config + src.database before this file imports them
from src.models import Base, CustomerHealth, HubSpotIntegration, Organization

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


def _make_mock_client(contacts=None, company=None, deals=None) -> MagicMock:
    mc = MagicMock()
    mc.list_contacts.return_value = contacts or []
    mc.get_company.return_value = company
    mc.get_open_deals_for_company.return_value = deals or []
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
        import src.tasks.hubspot_sync as hs
        importlib.reload(hs)

        with patch.object(hs, "get_db_session", _fake_db_session):
            result = hs._sync_org(org_id, db, mock_client)

        return result, health_mock
    finally:
        sys.modules.pop("src.services.health_score_service", None)


# ---------------------------------------------------------------------------
# Phase 1: TestModelsAndMigration
# ---------------------------------------------------------------------------


class TestModelsAndMigration:
    def test_crm_enrichment_table_creates_on_sqlite(self):
        """CrmEnrichment table must be creatable (already done in _fresh_db fixture)."""
        from src.models import CrmEnrichment  # noqa: F401
        assert "crm_enrichment" in Base.metadata.tables

    def test_worker_and_backend_crm_enrichment_columns_match(self):
        """Worker mirror columns must exactly match backend-api model columns.

        The backend model is imported by temporarily swapping sys.path and
        sys.modules so the worker's 'src' package is not shadowed.
        """
        import os

        # Worker mirror (available in current sys.path)
        from src.models import CrmEnrichment as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        # Temporarily save worker's src-related modules and path
        worktree = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        backend_src = os.path.join(worktree, "services", "backend-api")

        # Save & clear conflicting modules
        saved_mods = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
        for k in saved_mods:
            del sys.modules[k]

        # Prepend backend-api to path so its 'src' is found first
        sys.path.insert(0, backend_src)
        try:
            from src.models.crm_enrichment import CrmEnrichment as BackendModel
            backend_cols = {c.name for c in BackendModel.__table__.columns}
        finally:
            # Restore worker's src modules
            sys.path.remove(backend_src)
            # Remove any backend-api src modules we imported
            for k in list(sys.modules.keys()):
                if k == "src" or k.startswith("src."):
                    del sys.modules[k]
            sys.modules.update(saved_mods)

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )

    def test_worker_and_backend_hubspot_integration_columns_match(self):
        """Worker HubSpotIntegration mirror columns must exactly match
        backend-api model columns (writeback-config-api aspect: extends the
        crm_enrichment-only parity coverage to HubSpotIntegration too).

        Same sys.path/sys.modules swap technique as the crm_enrichment parity
        test above.
        """
        import os

        # Worker mirror (available in current sys.path)
        from src.models import HubSpotIntegration as WorkerModel
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
            from src.models.hubspot_integration import HubSpotIntegration as BackendModel
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

    def test_churn_label_suggestions_table_creates_on_sqlite(self):
        """ChurnLabelSuggestion table must be creatable (already done in _fresh_db fixture)."""
        from src.models import ChurnLabelSuggestion  # noqa: F401
        assert "churn_label_suggestions" in Base.metadata.tables

    def test_worker_and_backend_churn_label_suggestion_columns_match(self):
        """Worker ChurnLabelSuggestion mirror columns must exactly match
        backend-api model columns (crm-churn-labels aspect, data-model).

        Same sys.path/sys.modules swap technique as the crm_enrichment parity
        test above.
        """
        import os

        # Worker mirror (available in current sys.path)
        from src.models import ChurnLabelSuggestion as WorkerModel
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
            from src.models.churn_label_suggestion import ChurnLabelSuggestion as BackendModel
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

    def test_worker_suggestion_mirror_has_no_foreign_keys(self):
        """Worker mirror carries no FKs — the worker cannot import backend code."""
        from src.models import ChurnLabelSuggestion as WorkerModel

        assert not [
            c for c in WorkerModel.__table__.columns if c.foreign_keys
        ]

    def test_worker_and_backend_salesforce_integration_columns_match(self):
        """Worker SalesforceIntegration mirror columns must exactly match
        backend-api model columns (crm-churn-labels aspect, data-model —
        new coverage; HubSpot is already covered above and auto-guards the
        two new opt-in columns since it diffs full column-name sets).

        Same sys.path/sys.modules swap technique as the crm_enrichment parity
        test above.
        """
        import os

        # Worker mirror (available in current sys.path)
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

    def test_crm_enrichment_unique_constraint_enforced(self, db):
        """Duplicate (organization_id, customer_email) must raise IntegrityError."""
        from src.models import CrmEnrichment

        now = datetime.utcnow()
        row1 = CrmEnrichment(
            organization_id=1,
            customer_email="alice@example.com",
            last_synced_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row1)
        db.commit()

        row2 = CrmEnrichment(
            organization_id=1,
            customer_email="alice@example.com",
            last_synced_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


# ---------------------------------------------------------------------------
# Phase 3: TestSyncOrgUpsert
# ---------------------------------------------------------------------------


class TestSyncOrgUpsert:
    def test_upsert_one_row_per_matched_email(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": "co1",
                    },
                }
            ],
            company={"name": "Acme", "annualrevenue": "50000"},
            deals=[],
        )

        _run_sync_org(org.id, db, client)

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1
        assert rows[0].organization_id == org.id
        assert rows[0].customer_email == "alice@example.com"
        assert rows[0].company_name == "Acme"
        assert rows[0].arr == 50000.0
        assert rows[0].renewal_date is None

    def test_unmatched_contact_not_upserted(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        # no customers in this org

        client = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "bob@example.com",
                        "lifecyclestage": "lead",
                        "associatedcompanyid": None,
                    },
                }
            ],
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
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": None,
                    },
                }
            ],
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
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": None,
                    },
                }
            ],
        )

        _run_sync_org(org1.id, db, client)

        org1_rows = db.query(CrmEnrichment).filter_by(organization_id=org1.id).all()
        org2_rows = db.query(CrmEnrichment).filter_by(organization_id=org2.id).all()
        assert len(org1_rows) == 1
        assert len(org2_rows) == 0


# ---------------------------------------------------------------------------
# Phase 3: TestSyncOrgIdempotency
# ---------------------------------------------------------------------------


class TestSyncOrgIdempotency:
    def test_idempotent_rerun_does_not_duplicate(self, db):
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": None,
                    },
                }
            ],
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
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": "co1",
                    },
                }
            ],
            company={"name": "Acme", "annualrevenue": "10000"},
        )
        _run_sync_org(org.id, db, client1)

        client2 = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": "co1",
                    },
                }
            ],
            company={"name": "Acme", "annualrevenue": "20000"},
        )
        _run_sync_org(org.id, db, client2)

        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1
        assert rows[0].arr == 20000.0


# ---------------------------------------------------------------------------
# Phase 3: TestRenewalProxySelection
# ---------------------------------------------------------------------------


class TestRenewalProxySelection:
    def _setup(self, db, deals):
        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        client = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": "co1",
                    },
                }
            ],
            company={"name": "Acme", "annualrevenue": "5000"},
            deals=deals,
        )
        return org, client

    def test_renewal_proxy_highest_amount_open_deal(self, db):
        from src.models import CrmEnrichment

        deals = [
            {
                "id": "d1",
                "properties": {
                    "amount": "5000",
                    "closedate": "2026-09-01T00:00:00Z",
                    "dealstage": "contractsent",
                    "dealname": "Deal One",
                },
            },
            {
                "id": "d2",
                "properties": {
                    "amount": "12000",
                    "closedate": "2026-10-01T00:00:00Z",
                    "dealstage": "appointmentscheduled",
                    "dealname": "Deal Two",
                },
            },
        ]
        org, client = self._setup(db, deals)
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.deal_amount == 12000.0
        assert row.hubspot_deal_id == "d2"
        assert row.renewal_date is not None

    def test_renewal_proxy_excludes_closed_won(self, db):
        from src.models import CrmEnrichment

        deals = [
            {
                "id": "d1",
                "properties": {
                    "amount": "99999",
                    "closedate": "2026-09-01T00:00:00Z",
                    "dealstage": "closedwon",
                    "dealname": "Closed Won Deal",
                },
            },
            {
                "id": "d2",
                "properties": {
                    "amount": "1000",
                    "closedate": "2026-10-01T00:00:00Z",
                    "dealstage": "contractsent",
                    "dealname": "Open Deal",
                },
            },
        ]
        org, client = self._setup(db, deals)
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.deal_amount == 1000.0
        assert row.hubspot_deal_id == "d2"

    def test_renewal_proxy_excludes_closed_lost(self, db):
        from src.models import CrmEnrichment

        deals = [
            {
                "id": "d1",
                "properties": {
                    "amount": "99999",
                    "closedate": "2026-09-01T00:00:00Z",
                    "dealstage": "closedlost",
                    "dealname": "Closed Lost Deal",
                },
            },
            {
                "id": "d2",
                "properties": {
                    "amount": "500",
                    "closedate": "2026-10-01T00:00:00Z",
                    "dealstage": "appointmentscheduled",
                    "dealname": "Open Deal",
                },
            },
        ]
        org, client = self._setup(db, deals)
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.deal_amount == 500.0
        assert row.hubspot_deal_id == "d2"

    def test_no_deals_gives_null_renewal(self, db):
        from src.models import CrmEnrichment

        org, client = self._setup(db, deals=[])
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.renewal_date is None
        assert row.deal_name is None
        assert row.deal_stage is None
        assert row.deal_amount is None

    def test_deal_without_closedate_excluded(self, db):
        from src.models import CrmEnrichment

        deals = [
            {
                "id": "dx",
                "properties": {
                    "amount": "99999",
                    "closedate": None,
                    "dealstage": "contractsent",
                    "dealname": "No Close Date Deal",
                },
            },
        ]
        org, client = self._setup(db, deals)
        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        assert row.renewal_date is None


# ---------------------------------------------------------------------------
# Phase 3: TestSyncOrgHealthRecompute
# ---------------------------------------------------------------------------


class TestSyncOrgHealthRecompute:
    def test_update_customer_health_called_once_per_matched_customer(self, db):
        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")
        _make_customer(db, org.id, "bob@example.com")

        client = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": None,
                    },
                },
                {
                    "id": "c2",
                    "properties": {
                        "email": "bob@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": None,
                    },
                },
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
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": None,
                    },
                }
            ],
        )

        # Remove the health_score_service from sys.modules to force ImportError path
        sys.modules["src.services.health_score_service"] = None

        try:
            import src.tasks.hubspot_sync as hs
            importlib.reload(hs)
            with patch.object(hs, "get_db_session", _fake_db_session):
                result = hs._sync_org(org.id, db, client)
        finally:
            sys.modules.pop("src.services.health_score_service", None)

        # Should not raise; CrmEnrichment row should still be written
        rows = db.query(CrmEnrichment).all()
        assert len(rows) == 1

    def test_unmatched_customer_health_not_called(self, db):
        org = _make_org(db)
        # No customers in org

        client = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "nobody@example.com",
                        "lifecyclestage": "lead",
                        "associatedcompanyid": None,
                    },
                }
            ],
        )

        health_mock = MagicMock()
        _run_sync_org(org.id, db, client, health_mock=health_mock)

        assert health_mock.update_customer_health.call_count == 0


# ---------------------------------------------------------------------------
# Phase 4: TestFanOutTask
# ---------------------------------------------------------------------------


class TestFanOutTask:
    def test_fanout_enqueues_active_integrations_only(self, db):
        active = HubSpotIntegration(
            organization_id=1,
            access_token="enc-token",
            is_active=True,
            connected_at=datetime.utcnow(),
            contacts_synced=0,
            contacts_matched=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        inactive = HubSpotIntegration(
            organization_id=2,
            access_token="enc-token2",
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

        import src.tasks.hubspot_sync as hs
        importlib.reload(hs)

        with patch.object(hs, "get_db_session", _fake_db_session), \
             patch.object(hs, "sync_hubspot_org") as mock_task:
            mock_task.delay = MagicMock()
            hs.sync_all_hubspot()

        mock_task.delay.assert_called_once_with(active.id)

    def test_fanout_one_org_raising_does_not_abort_others(self, db):
        integ1 = HubSpotIntegration(
            organization_id=1, access_token="t1", is_active=True,
            connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        integ2 = HubSpotIntegration(
            organization_id=2, access_token="t2", is_active=True,
            connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        integ3 = HubSpotIntegration(
            organization_id=3, access_token="t3", is_active=True,
            connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add_all([integ1, integ2, integ3])
        db.commit()

        import src.tasks.hubspot_sync as hs
        importlib.reload(hs)

        call_count = 0

        def _side_effect(integration_id):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated failure on second org")

        with patch.object(hs, "get_db_session", _fake_db_session), \
             patch.object(hs, "sync_hubspot_org") as mock_task:
            mock_task.delay = MagicMock(side_effect=_side_effect)
            hs.sync_all_hubspot()

        assert mock_task.delay.call_count == 3

    def test_fanout_no_active_integrations_returns_zero(self, db):
        import src.tasks.hubspot_sync as hs
        importlib.reload(hs)

        with patch.object(hs, "get_db_session", _fake_db_session), \
             patch.object(hs, "sync_hubspot_org") as mock_task:
            mock_task.delay = MagicMock()
            result = hs.sync_all_hubspot()

        assert result["status"] == "no_integrations"
        assert result["queued"] == 0


# ---------------------------------------------------------------------------
# Phase 4: TestCeleryTaskRegistration
# ---------------------------------------------------------------------------


class TestCeleryTaskRegistration:
    def test_sync_all_hubspot_is_registered(self):
        from src.celery_app import celery_app
        assert "src.tasks.hubspot_sync.sync_all_hubspot" in celery_app.tasks

    def test_sync_hubspot_org_is_registered(self):
        from src.celery_app import celery_app
        assert "src.tasks.hubspot_sync.sync_hubspot_org" in celery_app.tasks

    def test_beat_schedule_has_hubspot_entry(self):
        from src.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "sync-hubspot-daily" in schedule
        entry = schedule["sync-hubspot-daily"]
        cron = entry["schedule"]
        assert cron.hour == {3}
        assert cron.minute == {15}  # 03:15 — avoids collision with refit-global-calibration-daily at 03:00


# ---------------------------------------------------------------------------
# Phase 6 (hardening): missing-key + transient-error tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 1 (provider-churn-fetch): characterization lock — pins the EXISTING
# enrichment output byte-identical before any client edit in this aspect.
# ---------------------------------------------------------------------------


# Fixed payload: 4 deals — open/high-amount, open/low, closedwon, closedlost.
# Amounts are chosen so a broken filter (e.g. closed_stages flipped to set())
# would pick a *different* deal than d1.
CHARACTERIZATION_PAYLOAD = [
    {
        "id": "d1",
        "properties": {
            "dealname": "Open High",
            "dealstage": "contractsent",
            "amount": "900",
            "closedate": "2026-09-01T00:00:00Z",
        },
    },
    {
        "id": "d2",
        "properties": {
            "dealname": "Open Low",
            "dealstage": "appointmentscheduled",
            "amount": "100",
            "closedate": "2026-08-01T00:00:00Z",
        },
    },
    {
        "id": "d3",
        "properties": {
            "dealname": "Won Big",
            "dealstage": "closedwon",
            "amount": "5000",
            "closedate": "2026-05-01T00:00:00Z",
        },
    },
    {
        "id": "d4",
        "properties": {
            "dealname": "Lost Big",
            "dealstage": "closedlost",
            "amount": "4000",
            "closedate": "2026-01-15T00:00:00Z",
        },
    },
]


class TestEnrichmentCharacterizationLock:
    def test_pick_renewal_deal_picks_d1(self):
        from src.tasks.hubspot_sync import _pick_renewal_deal

        assert _pick_renewal_deal(CHARACTERIZATION_PAYLOAD) is CHARACTERIZATION_PAYLOAD[0]

    def test_pick_renewal_deal_ignores_closed_and_dateless(self):
        from src.tasks.hubspot_sync import _pick_renewal_deal

        winner = _pick_renewal_deal(CHARACTERIZATION_PAYLOAD)
        assert winner["id"] != "d3"
        assert winner["id"] != "d4"
        # d3/d4 have higher raw amounts (5000, 4000) than the winner (900) —
        # proves the closed-stage exclusion, not just amount ranking.
        assert winner["properties"]["amount"] == "900"

    def test_enrichment_row_fields_are_exact(self, db):
        from datetime import datetime
        from src.models import CrmEnrichment

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": "co1",
                    },
                }
            ],
            company={"name": "Acme", "annualrevenue": "5000"},
            deals=CHARACTERIZATION_PAYLOAD,
        )

        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        actual = {
            "deal_name": row.deal_name,
            "deal_stage": row.deal_stage,
            "deal_amount": row.deal_amount,
            "renewal_date": row.renewal_date,
            "hubspot_deal_id": row.hubspot_deal_id,
        }
        expected = {
            "deal_name": "Open High",
            "deal_stage": "contractsent",
            "deal_amount": 900.0,
            "renewal_date": datetime(2026, 9, 1),
            "hubspot_deal_id": "d1",
        }
        assert actual == expected
        assert actual["deal_stage"] != "closedlost"

    def test_enrichment_row_unchanged_when_pipeline_present_on_every_deal(self, db):
        """Phase 6 lock extension: adding `pipeline` to every deal's properties
        must not change the enrichment row — the sync reads named keys only."""
        import copy
        from datetime import datetime
        from src.models import CrmEnrichment

        payload_with_pipeline = copy.deepcopy(CHARACTERIZATION_PAYLOAD)
        for deal in payload_with_pipeline:
            deal["properties"]["pipeline"] = "default"

        org = _make_org(db)
        _make_customer(db, org.id, "alice@example.com")

        client = _make_mock_client(
            contacts=[
                {
                    "id": "c1",
                    "properties": {
                        "email": "alice@example.com",
                        "lifecyclestage": "customer",
                        "associatedcompanyid": "co1",
                    },
                }
            ],
            company={"name": "Acme", "annualrevenue": "5000"},
            deals=payload_with_pipeline,
        )

        _run_sync_org(org.id, db, client)

        row = db.query(CrmEnrichment).first()
        actual = {
            "deal_name": row.deal_name,
            "deal_stage": row.deal_stage,
            "deal_amount": row.deal_amount,
            "renewal_date": row.renewal_date,
            "hubspot_deal_id": row.hubspot_deal_id,
        }
        expected = {
            "deal_name": "Open High",
            "deal_stage": "contractsent",
            "deal_amount": 900.0,
            "renewal_date": datetime(2026, 9, 1),
            "hubspot_deal_id": "d1",
        }
        assert actual == expected
        assert not hasattr(row, "pipeline")


class TestHardeningEdgeCases:
    def test_sync_hubspot_org_missing_encryption_key(self, db):
        """Task returns error dict without raising when LLM_ENCRYPTION_KEY unset."""
        integ = HubSpotIntegration(
            organization_id=1, access_token="enc", is_active=True,
            connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)

        import src.tasks.hubspot_sync as hs
        importlib.reload(hs)

        with patch.object(hs, "get_db_session", _fake_db_session), \
             patch.object(hs, "_decrypt", side_effect=ValueError("LLM_ENCRYPTION_KEY is not set")):
            # Call the inner body directly (not via Celery) — bind=True tasks
            # need a self mock
            task_self = MagicMock()
            result = hs._sync_hubspot_org_body(task_self, integ.id)

        assert result["status"] == "error"
        assert result["reason"] == "missing_encryption_key"

    def test_sync_hubspot_org_retries_on_transient_error(self, db):
        """Task calls self.retry when HubSpotTransientError raised."""
        from celery.exceptions import Retry

        integ = HubSpotIntegration(
            organization_id=1, access_token="enc", is_active=True,
            connected_at=datetime.utcnow(), contacts_synced=0, contacts_matched=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(integ)
        db.commit()
        db.refresh(integ)

        import src.tasks.hubspot_sync as hs
        importlib.reload(hs)

        task_self = MagicMock()
        # self.retry should raise Retry (that's how Celery works)
        task_self.retry.side_effect = Retry()

        # Patch HubSpotClient in the task module's namespace (not the source module)
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.list_contacts.side_effect = hs.HubSpotTransientError("rate limited")

        with patch.object(hs, "get_db_session", _fake_db_session), \
             patch.object(hs, "_decrypt", return_value="plain-token"), \
             patch.object(hs, "HubSpotClient", return_value=mock_client_instance):
            with pytest.raises(Retry):
                hs._sync_hubspot_org_body(task_self, integ.id)

        task_self.retry.assert_called_once()
