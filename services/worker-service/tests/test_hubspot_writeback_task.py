"""
TDD tests for the push_health_to_hubspot writeback task
(writeback-task-trigger aspect, Phase 1).

Strategy: in-memory SQLite, mocked HubSpotClient, NO Celery eager mode.
Mirrors tests/test_hubspot_sync.py structure (own engine, own db fixture,
module reload + patch.object(hw, "get_db_session", ...) idiom).
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

from src.models import Base, CrmEnrichment, CustomerHealth, HubSpotIntegration, Organization

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


def _make_integration(db: Session, org_id: int, **overrides) -> HubSpotIntegration:
    now = datetime.utcnow()
    defaults = dict(
        organization_id=org_id,
        access_token="enc-token",
        is_active=True,
        writeback_enabled=True,
        writeback_field_name="rereflect_health_score",
        connected_at=now,
        contacts_synced=0,
        contacts_matched=0,
        contacts_written=0,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    row = HubSpotIntegration(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_enrichment(db: Session, org_id: int, email: str, **overrides) -> CrmEnrichment:
    now = datetime.utcnow()
    defaults = dict(
        organization_id=org_id,
        customer_email=email,
        hubspot_contact_id="contact-1",
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


def _make_mock_client(prop_def=_UNSET) -> MagicMock:
    """MagicMock HubSpotClient with context-manager support.

    Defaults: property def exists (truthy), PATCH succeeds (no exception).
    Pass prop_def=None explicitly to simulate a 404 on the property lookup.
    """
    mc = MagicMock()
    mc.__enter__ = MagicMock(return_value=mc)
    mc.__exit__ = MagicMock(return_value=False)
    mc.get_contact_property_def.return_value = (
        {"name": "rereflect_health_score", "type": "number"} if prop_def is _UNSET else prop_def
    )
    mc.update_contact_property.return_value = None
    return mc


def _reload_task_module():
    import src.tasks.hubspot_writeback as hw
    importlib.reload(hw)
    return hw


def _run_push(org_id, email, mock_client=None, task_self=None, decrypt_ok=True):
    """Call _push_health_to_hubspot_body with test doubles wired in."""
    hw = _reload_task_module()
    if task_self is None:
        task_self = MagicMock()
    if mock_client is None:
        mock_client = _make_mock_client()

    patches = [
        patch.object(hw, "get_db_session", _fake_db_session),
        patch.object(hw, "HubSpotClient", return_value=mock_client),
    ]
    if decrypt_ok:
        patches.append(patch.object(hw, "_decrypt", return_value="plain-token"))

    with patches[0], patches[1]:
        if decrypt_ok:
            with patches[2]:
                result = hw._push_health_to_hubspot_body(task_self, org_id, email)
        else:
            result = hw._push_health_to_hubspot_body(task_self, org_id, email)

    return result, hw, mock_client


# ---------------------------------------------------------------------------
# TestNoOpGuards
# ---------------------------------------------------------------------------


class TestNoOpGuards:
    def test_integration_inactive_no_patch(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, is_active=False)
        _make_enrichment(db, org.id, "alice@example.com")
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "noop"
        mock_client.update_contact_property.assert_not_called()

    def test_no_integration_row_no_patch(self, db):
        org = _make_org(db)
        _make_enrichment(db, org.id, "alice@example.com")
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "noop"
        mock_client.update_contact_property.assert_not_called()

    def test_writeback_disabled_no_patch(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_enabled=False)
        _make_enrichment(db, org.id, "alice@example.com")
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "noop"
        mock_client.update_contact_property.assert_not_called()

    def test_no_field_name_no_patch(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_field_name=None)
        _make_enrichment(db, org.id, "alice@example.com")
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "noop"
        mock_client.update_contact_property.assert_not_called()

    def test_no_enrichment_row_no_patch(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "noop"
        mock_client.update_contact_property.assert_not_called()

    def test_no_hubspot_contact_id_no_patch(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", hubspot_contact_id=None)
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "noop"
        mock_client.update_contact_property.assert_not_called()

    def test_score_equals_last_written_no_patch(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=80)
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "noop"
        mock_client.update_contact_property.assert_not_called()

    def test_change_under_two_points_no_patch(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=80)
        _make_health(db, org.id, "alice@example.com", 81)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "noop"
        mock_client.update_contact_property.assert_not_called()

    def test_first_push_with_no_last_written_proceeds(self, db):
        """last_written_health_score is None (never pushed) -> not a no-op,
        regardless of how small the current score is."""
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=None)
        _make_health(db, org.id, "alice@example.com", 1)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "ok"
        mock_client.update_contact_property.assert_called_once()


# ---------------------------------------------------------------------------
# TestHappyPath
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_patch_called_once_with_correct_args(self, db):
        org = _make_org(db)
        _make_integration(db, org.id, writeback_field_name="rereflect_health_score")
        _make_enrichment(
            db, org.id, "alice@example.com",
            hubspot_contact_id="contact-99", last_written_health_score=50,
        )
        _make_health(db, org.id, "alice@example.com", 80)

        result, _, mock_client = _run_push(org.id, "alice@example.com")

        assert result["status"] == "ok"
        mock_client.update_contact_property.assert_called_once_with(
            "contact-99", "rereflect_health_score", 80
        )

    def test_success_updates_enrichment_and_integration_rows(self, db):
        org = _make_org(db)
        integ = _make_integration(db, org.id, contacts_written=2)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        _run_push(org.id, "alice@example.com")

        db.expire_all()
        enrichment = db.query(CrmEnrichment).filter_by(
            organization_id=org.id, customer_email="alice@example.com"
        ).first()
        integration = db.query(HubSpotIntegration).filter_by(organization_id=org.id).first()

        assert enrichment.last_written_health_score == 80
        assert enrichment.last_health_written_at is not None
        assert integration.last_writeback_status == "ok"
        assert integration.last_writeback_error is None
        assert integration.last_writeback_at is not None
        assert integration.contacts_written == 3


# ---------------------------------------------------------------------------
# TestSoftPauseScopeError
# ---------------------------------------------------------------------------


class TestSoftPauseScopeError:
    def test_403_sets_missing_write_scope_status(self, db):
        from src.clients.hubspot import HubSpotScopeError

        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_property.side_effect = HubSpotScopeError("no write scope")

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result["status"] == "error"
        assert result["reason"] == "missing_write_scope"

        db.expire_all()
        integration = db.query(HubSpotIntegration).filter_by(organization_id=org.id).first()
        assert integration.last_writeback_status == "error: missing_write_scope"
        assert integration.is_active is True  # never touched by writeback

    def test_403_does_not_break_subsequent_read_sync(self, db):
        """R-critical: soft-pause on 403 must never touch is_active; an inbound
        sync_hubspot_org call afterwards must still succeed."""
        from src.clients.hubspot import HubSpotScopeError

        org = _make_org(db)
        integ = _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_property.side_effect = HubSpotScopeError("no write scope")
        _run_push(org.id, "alice@example.com", mock_client=mock_client)

        # Now run the read-sync task body against the same integration.
        import src.tasks.hubspot_sync as sync_mod
        importlib.reload(sync_mod)

        sync_client = MagicMock()
        sync_client.__enter__ = MagicMock(return_value=sync_client)
        sync_client.__exit__ = MagicMock(return_value=False)
        sync_client.list_contacts.return_value = []

        with patch.object(sync_mod, "get_db_session", _fake_db_session), \
             patch.object(sync_mod, "_decrypt", return_value="plain-token"), \
             patch.object(sync_mod, "HubSpotClient", return_value=sync_client):
            task_self = MagicMock()
            sync_result = sync_mod._sync_hubspot_org_body(task_self, integ.id)

        assert sync_result["status"] == "success"


# ---------------------------------------------------------------------------
# TestFieldNotFound
# ---------------------------------------------------------------------------


class TestFieldNotFound:
    def test_property_404_sets_field_not_found_status(self, db):
        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client(prop_def=None)  # 404 on GET/def

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result["status"] == "error"
        assert result["reason"] == "field_not_found"
        mock_client.update_contact_property.assert_not_called()

        db.expire_all()
        integration = db.query(HubSpotIntegration).filter_by(organization_id=org.id).first()
        assert integration.last_writeback_status == "field_not_found"
        assert integration.is_active is True


# ---------------------------------------------------------------------------
# TestContactNotFound
# ---------------------------------------------------------------------------


class TestContactNotFound:
    def test_contact_404_skips_customer_without_global_failure(self, db):
        from src.clients.hubspot import HubSpotNotFoundError

        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_property.side_effect = HubSpotNotFoundError("contact gone")

        result, _, _ = _run_push(org.id, "alice@example.com", mock_client=mock_client)

        assert result["status"] == "error"
        assert result["reason"] == "contact_not_found"

        db.expire_all()
        integration = db.query(HubSpotIntegration).filter_by(organization_id=org.id).first()
        assert integration.last_writeback_status == "contact_not_found"
        assert integration.is_active is True


# ---------------------------------------------------------------------------
# TestTransientRetry
# ---------------------------------------------------------------------------


class TestTransientRetry:
    def test_transient_error_triggers_retry(self, db):
        from celery.exceptions import Retry
        from src.clients.hubspot import HubSpotTransientError

        org = _make_org(db)
        _make_integration(db, org.id)
        _make_enrichment(db, org.id, "alice@example.com", last_written_health_score=50)
        _make_health(db, org.id, "alice@example.com", 80)

        mock_client = _make_mock_client()
        mock_client.update_contact_property.side_effect = HubSpotTransientError("rate limited")

        task_self = MagicMock()
        task_self.retry.side_effect = Retry()

        with pytest.raises(Retry):
            _run_push(org.id, "alice@example.com", mock_client=mock_client, task_self=task_self)

        # Mirrors hubspot_sync.py's retry test: the DB write to "retrying" is
        # rolled back along with the rest of the session when self.retry()
        # raises (get_db_session's except-block calls rollback()); only the
        # retry() invocation itself is asserted, matching existing precedent.
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

        hw = _reload_task_module()
        task_self = MagicMock()

        with patch.object(hw, "get_db_session", _fake_db_session), \
             patch.object(hw, "_decrypt", side_effect=ValueError("LLM_ENCRYPTION_KEY is not set")):
            result = hw._push_health_to_hubspot_body(task_self, org.id, "alice@example.com")

        assert result["status"] == "error"
        assert result["reason"] == "missing_encryption_key"
        task_self.retry.assert_not_called()


# ---------------------------------------------------------------------------
# TestCeleryTaskRegistration
# ---------------------------------------------------------------------------


class TestCeleryTaskRegistration:
    def test_push_health_to_hubspot_is_registered_with_exact_name(self):
        from src.celery_app import celery_app
        assert "src.tasks.hubspot_writeback.push_health_to_hubspot" in celery_app.tasks
