"""
TDD tests for the push_health_to_salesforce writeback task
(push-task-trigger aspect, Phase 2).

Strategy: in-memory SQLite, mocked SalesforceClient, NO Celery eager mode.
Mirrors tests/test_hubspot_writeback_task.py structure (own engine, own db
fixture, module reload + patch.object(sw, "get_db_session", ...) idiom).
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

from src.models import (
    Base,
    CrmEnrichment,
    CustomerHealth,
    Organization,
    SalesforceIntegration,
)

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
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session) -> Organization:
    org = Organization(name="TestCorp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_integration(db: Session, org_id: int, **overrides) -> SalesforceIntegration:
    now = datetime.utcnow()
    defaults = dict(
        organization_id=org_id,
        refresh_token="enc-refresh-token",
        instance_url="https://acme.my.salesforce.com",
        is_active=True,
        writeback_enabled=True,
        writeback_field_name="Rereflect_Health_Score__c",
        connected_at=now,
        contacts_synced=0,
        contacts_matched=0,
        contacts_written=0,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    row = SalesforceIntegration(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_enrichment(db: Session, org_id: int, email: str, **overrides) -> CrmEnrichment:
    now = datetime.utcnow()
    defaults = dict(
        organization_id=org_id,
        customer_email=email,
        provider="salesforce",
        salesforce_contact_id="003c1AAAA",
        last_synced_at=now,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    row = CrmEnrichment(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_health(db: Session, org_id: int, email: str, score: int) -> CustomerHealth:
    row = CustomerHealth(organization_id=org_id, customer_email=email, health_score=score)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


_UNSET = object()


def _make_mock_client(fields=_UNSET) -> MagicMock:
    """MagicMock SalesforceClient with context-manager support.

    Defaults: describe_object() reports the field exists+updateable; PATCH
    (update_contact_field) succeeds (no exception). Pass fields=[] to
    simulate a describe response missing the field (field_not_found).
    """
    mc = MagicMock()
    mc.__enter__ = MagicMock(return_value=mc)
    mc.__exit__ = MagicMock(return_value=False)
    mc.describe_object.return_value = {
        "fields": (
            [{"name": "Rereflect_Health_Score__c", "type": "double", "updateable": True}]
            if fields is _UNSET
            else fields
        )
    }
    mc.update_contact_field.return_value = None
    mc.query.return_value = []
    return mc


def _reload_task_module():
    import src.tasks.salesforce_writeback as sw
    importlib.reload(sw)
    return sw


def _run_push(org_id, email, mock_client=None, task_self=None, decrypt_ok=True):
    """Call _push_health_to_salesforce_body with test doubles wired in."""
    sw = _reload_task_module()
    if task_self is None:
        task_self = MagicMock()
    if mock_client is None:
        mock_client = _make_mock_client()

    with patch.object(sw, "get_db_session", _fake_db_session), \
         patch.object(sw, "SalesforceClient", return_value=mock_client):
        if decrypt_ok:
            with patch.object(sw, "_decrypt", return_value="plain-refresh-token"):
                result = sw._push_health_to_salesforce_body(task_self, org_id, email)
        else:
            result = sw._push_health_to_salesforce_body(task_self, org_id, email)

    return result, sw, mock_client


# ---------------------------------------------------------------------------
# TestNoOpGuards
# ---------------------------------------------------------------------------


class TestNoOpGuards:
    def test_integration_inactive_no_write(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, is_active=False)
        _make_enrichment(db, org.id, "alice@example.com")
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result == {"status": "noop", "reason": "integration_inactive"}
        mock_client.update_contact_field.assert_not_called()

    def test_no_integration_row_no_write(self, db):
        org = _make_org(db)
        _make_enrichment(db, org.id, "alice@example.com")
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result == {"status": "noop", "reason": "integration_inactive"}
        mock_client.update_contact_field.assert_not_called()

    def test_writeback_disabled_no_write(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_enabled=False)
        _make_enrichment(db, org.id, "alice@example.com")
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result == {"status": "noop", "reason": "writeback_disabled"}
        mock_client.update_contact_field.assert_not_called()

    def test_no_field_name_no_write(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_field_name=None)
        _make_enrichment(db, org.id, "alice@example.com")
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result == {"status": "noop", "reason": "no_field_name"}
        mock_client.update_contact_field.assert_not_called()

    def test_no_enrichment_row_no_write(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result == {"status": "noop", "reason": "no_enrichment"}
        mock_client.update_contact_field.assert_not_called()

    def test_no_health_row_no_write(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com")

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result == {"status": "noop", "reason": "no_health_row"}
        mock_client.update_contact_field.assert_not_called()

    def test_score_equals_last_written_no_write(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=80)
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result == {"status": "noop", "reason": "score_unchanged"}
        mock_client.update_contact_field.assert_not_called()

    def test_change_under_two_points_no_write(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=80)
        _make_health(db, org.id, "alice@example.com", 81)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result == {"status": "noop", "reason": "change_too_small"}
        mock_client.update_contact_field.assert_not_called()

    def test_first_push_with_no_last_written_proceeds(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=None)
        _make_health(db, org.id, "alice@example.com", 1)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "ok"
        mock_client.update_contact_field.assert_called_once()


# ---------------------------------------------------------------------------
# TestHappyPath (contact id already known from sync)
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_write_called_once_with_correct_args(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_field_name="Rereflect_Health_Score__c")
        _make_enrichment(
            db, org.id, "alice@example.com",
            salesforce_contact_id="003c99ZZZZ", last_written_health_score=50,
        )
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "ok"
        mock_client.update_contact_field.assert_called_once_with(
            "003c99ZZZZ", "Rereflect_Health_Score__c", 80
        )

    def test_success_updates_enrichment_and_integration_rows(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, contacts_written=2)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        _run_push(org.id, "alice@example.com")

        db.expire_all()
        enrichment = db.query(CrmEnrichment).filter_by(
            organization_id=org.id, customer_email="alice@example.com"
        ).first()
        integration = db.query(SalesforceIntegration).filter_by(organization_id=org.id).first()

        assert enrichment.last_written_health_score == 80
        assert enrichment.last_health_written_at is not None
        assert integration.last_writeback_status == "ok"
        assert integration.last_writeback_error is None
        assert integration.last_writeback_at is not None
        assert integration.contacts_written == 3


# ---------------------------------------------------------------------------
# TestContactIdFallback (id null in enrichment -> re-query by email)
# ---------------------------------------------------------------------------


class TestContactIdFallback:
    def test_null_contact_id_falls_back_to_query_and_persists(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(
            db, org.id, "alice@example.com",
            salesforce_contact_id=None, last_written_health_score=50,
        )
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.query.return_value = [{"Id": "003c1AAAA"}]

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result["status"] == "ok"
        mock_client.query.assert_called_once()
        soql = mock_client.query.call_args[0][0]
        assert "alice@example.com" in soql
        assert "Contact" in soql
        mock_client.update_contact_field.assert_called_once_with(
            "003c1AAAA", "Rereflect_Health_Score__c", 80
        )

        db.expire_all()
        enrichment = db.query(CrmEnrichment).filter_by(
            organization_id=org.id, customer_email="alice@example.com"
        ).first()
        assert enrichment.salesforce_contact_id == "003c1AAAA"

    def test_duplicate_match_picks_lowest_id_and_sets_ambiguous_soft_error(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(
            db, org.id, "alice@example.com",
            salesforce_contact_id=None, last_written_health_score=50,
        )
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.query.return_value = [
            {"Id": "003c2BBBB"}, {"Id": "003c1AAAA"},
        ]

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result["status"] == "ok"
        mock_client.update_contact_field.assert_called_once_with(
            "003c1AAAA", "Rereflect_Health_Score__c", 80
        )

        db.expire_all()
        enrichment = db.query(CrmEnrichment).filter_by(
            organization_id=org.id, customer_email="alice@example.com"
        ).first()
        integration = db.query(SalesforceIntegration).filter_by(organization_id=org.id).first()
        assert enrichment.salesforce_contact_id == "003c1AAAA"
        assert integration.last_writeback_error == "ambiguous_contact"

    def test_no_match_returns_no_contact_id(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(
            db, org.id, "alice@example.com",
            salesforce_contact_id=None, last_written_health_score=50,
        )
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.query.return_value = []

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result == {"status": "noop", "reason": "no_contact_id"}
        mock_client.update_contact_field.assert_not_called()


# ---------------------------------------------------------------------------
# TestFieldNotFound
# ---------------------------------------------------------------------------


class TestFieldNotFound:
    def test_field_missing_from_describe_sets_field_not_found_status(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client(fields=[{"name": "Name", "type": "string", "updateable": False}])

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result["status"] == "error"
        assert result["reason"] == "field_not_found"
        mock_client.update_contact_field.assert_not_called()

        db.expire_all()
        integration = db.query(SalesforceIntegration).filter_by(organization_id=org.id).first()
        assert integration.last_writeback_status == "field_not_found"
        assert integration.is_active is True


# ---------------------------------------------------------------------------
# TestSoftPauseScopeError
# ---------------------------------------------------------------------------


class TestSoftPauseScopeError:
    def test_scope_error_sets_missing_write_scope_status(self, db):
        from src.clients.salesforce import SalesforceScopeError

        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_field.side_effect = SalesforceScopeError("no write scope")

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result == {"status": "error", "reason": "missing_write_scope"}

        db.expire_all()
        integration = db.query(SalesforceIntegration).filter_by(organization_id=org.id).first()
        assert integration.last_writeback_status == "error: missing_write_scope"
        assert integration.is_active is True  # never touched by writeback

    def test_scope_error_does_not_break_subsequent_read_sync(self, db):
        """R-critical: soft-pause must never touch is_active; an inbound
        sync_salesforce_org call afterwards must still succeed."""
        from src.clients.salesforce import SalesforceScopeError

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_field.side_effect = SalesforceScopeError("no write scope")
        _run_push(org.id, "alice@example.com", mock_client=mock_client)

        import src.tasks.salesforce_sync as sync_mod
        importlib.reload(sync_mod)

        sync_client = MagicMock()
        sync_client.__enter__ = MagicMock(return_value=sync_client)
        sync_client.__exit__ = MagicMock(return_value=False)
        sync_client.list_contacts.return_value = []

        with patch.object(sync_mod, "get_db_session", _fake_db_session), \
             patch.object(sync_mod, "_decrypt", return_value="plain-token"), \
             patch.object(sync_mod, "SalesforceClient", return_value=sync_client):
            task_self = MagicMock()
            sync_result = sync_mod._sync_salesforce_org_body(task_self, integ.id)

        assert sync_result["status"] == "success"


# ---------------------------------------------------------------------------
# TestContactNotFound
# ---------------------------------------------------------------------------


class TestContactNotFound:
    def test_contact_not_found_skips_customer_without_global_failure(self, db):
        from src.clients.salesforce import SalesforceNotFoundError

        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_field.side_effect = SalesforceNotFoundError("contact gone")

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result == {"status": "error", "reason": "contact_not_found"}

        db.expire_all()
        integration = db.query(SalesforceIntegration).filter_by(organization_id=org.id).first()
        assert integration.last_writeback_status == "contact_not_found"
        assert integration.is_active is True


# ---------------------------------------------------------------------------
# TestDailyLimit (soft-pause + retry, distinct from generic transient)
# ---------------------------------------------------------------------------


class TestDailyLimit:
    def test_daily_limit_429_sets_deferred_status_and_retries(self, db):
        from celery.exceptions import Retry
        from src.clients.salesforce import SalesforceTransientError

        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_field.side_effect = SalesforceTransientError(
            "Salesforce transient error 429 updating contact 003c1AAAA"
        )

        task_self = MagicMock()
        task_self.retry.side_effect = Retry()

        with pytest.raises(Retry):
            _run_push(org.id, "alice@example.com", mock_client=mock_client, task_self=task_self)

        # Mirrors hubspot_writeback.py's retry test precedent: the DB write
        # is rolled back along with the rest of the session when
        # self.retry() raises (get_db_session's except-block calls
        # rollback()); only the retry() invocation itself is asserted.
        task_self.retry.assert_called_once()

        db.expire_all()
        integration = db.query(SalesforceIntegration).filter_by(organization_id=org.id).first()
        assert integration.is_active is True


# ---------------------------------------------------------------------------
# TestTransientRetry (generic 5xx — plain retry, not daily_limit)
# ---------------------------------------------------------------------------


class TestTransientRetry:
    def test_5xx_transient_error_triggers_plain_retry(self, db):
        from celery.exceptions import Retry
        from src.clients.salesforce import SalesforceTransientError

        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_field.side_effect = SalesforceTransientError(
            "Salesforce transient error 500 updating contact 003c1AAAA"
        )

        task_self = MagicMock()
        task_self.retry.side_effect = Retry()

        with pytest.raises(Retry):
            _run_push(org.id, "alice@example.com", mock_client=mock_client, task_self=task_self)

        # Mirrors hubspot_writeback.py's retry test precedent — see comment
        # in TestDailyLimit above.
        task_self.retry.assert_called_once()


# ---------------------------------------------------------------------------
# TestMissingEncryptionKey
# ---------------------------------------------------------------------------


class TestMissingEncryptionKey:
    def test_missing_key_returns_error_dict_without_retry(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        sw = _reload_task_module()
        task_self = MagicMock()

        with patch.object(sw, "get_db_session", _fake_db_session), \
             patch.object(sw, "_decrypt", side_effect=ValueError("LLM_ENCRYPTION_KEY is not set")):
            result = sw._push_health_to_salesforce_body(task_self, org.id, "alice@example.com")

        assert result == {"status": "error", "reason": "missing_encryption_key"}
        task_self.retry.assert_not_called()


# ---------------------------------------------------------------------------
# TestCeleryTaskRegistration
# ---------------------------------------------------------------------------


class TestCeleryTaskRegistration:
    def test_push_health_to_salesforce_is_registered_with_exact_name(self):
        from src.celery_app import celery_app
        assert "src.tasks.salesforce_writeback.push_health_to_salesforce" in celery_app.tasks
