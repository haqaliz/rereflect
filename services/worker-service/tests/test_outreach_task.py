"""
Tests for the per-recipient outreach Celery task (bulk-campaign-api aspect).

Phase 1 — worker model mirrors (RED-first):
  - `OutreachCampaign` / `OutreachCampaignRecipient` exist on the worker `Base`
    metadata with the exact column sets of the outreach-core migration
    (f6a7b8c9d0e1), and `Organization.product_name_display` exists on the
    worker Organization mirror.

Phase 2 — task orchestration (RED-first):
  - sender-result mapping (ok→sent, skipped→skipped+reason, failed→failed+reason)
  - terminal-guard: an already-terminal recipient is a no-op (no sender call)
  - campaign `done` only when all recipients are terminal
  - defensive `queued→in_progress` flip when the route never set it
  - missing recipient → error dict, no raise
  - task-level exception → recipient `failed`, no re-raise

The sender's own opt-out/cooldown/no-key behavior is outreach-core's contract
(test_outreach_sender.py) — it is mocked here; this file tests the task's
orchestration only.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    Organization,
    OutreachCampaign,
    OutreachCampaignRecipient,
    CustomerHealth,
)

# ---------------------------------------------------------------------------
# In-memory DB wiring
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(db, name: str = "Task Org", product_name: str = "Taskly") -> Organization:
    org = Organization(name=name, plan="business", product_name_display=product_name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_campaign(db, org_id: int, status: str = "in_progress", recipient_count: int = 1,
                   subject: str = "We'd love your feedback", body: str = "Hi there") -> OutreachCampaign:
    campaign = OutreachCampaign(
        organization_id=org_id,
        created_by_user_id=None,
        subject=subject,
        body=body,
        recipient_count=1,
        status=status,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def _make_recipient(db, campaign_id: int, email: str, status: str = "queued",
                    error=None) -> OutreachCampaignRecipient:
    recipient = OutreachCampaignRecipient(
        campaign_id=campaign_id,
        customer_email=email,
        status=status,
        error=error,
    )
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient


def _get_tasks():
    import src.tasks.outreach as outreach_tasks
    return outreach_tasks


# ---------------------------------------------------------------------------
# Phase 1 — worker model mirrors
# ---------------------------------------------------------------------------

class TestWorkerModelMirrors:
    def test_outreach_campaign_mirror_table_columns(self):
        assert "outreach_campaigns" in Base.metadata.tables
        cols = {c.name for c in Base.metadata.tables["outreach_campaigns"].columns}
        assert cols == {
            "id", "organization_id", "created_by_user_id",
            "subject", "body", "recipient_count", "status", "created_at",
        }

    def test_outreach_campaign_recipients_mirror_table_columns(self):
        assert "outreach_campaign_recipients" in Base.metadata.tables
        cols = {c.name for c in Base.metadata.tables["outreach_campaign_recipients"].columns}
        assert cols == {
            "id", "campaign_id", "customer_email", "status", "error", "created_at",
        }

    def test_organization_mirror_has_product_name_display(self):
        assert hasattr(Organization, "product_name_display")

    def test_mirror_classes_importable_from_src_models(self):
        assert OutreachCampaign.__tablename__ == "outreach_campaigns"
        assert OutreachCampaignRecipient.__tablename__ == "outreach_campaign_recipients"


# ---------------------------------------------------------------------------
# Phase 2 — task orchestration
# ---------------------------------------------------------------------------

class TestSendOutreachEmailTask:
    def _patch_db_session(self, monkeypatch, db):
        from contextlib import contextmanager
        import src.tasks.outreach as task_mod

        @contextmanager
        def fake_get_db():
            yield db

        monkeypatch.setattr(task_mod, "get_db_session", fake_get_db)

    def test_ok_result_maps_to_sent(self, db, monkeypatch):
        org = _make_org(db)
        campaign = _make_campaign(db, org.id)
        recipient = _make_recipient(db, campaign.id, "a@test.com")
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            return_value={"ok": True, "status": "sent", "reason": ""},
        ) as mock_send:
            result = _get_tasks().send_outreach_email(campaign.id, recipient.id)

        assert result["status"] == "sent"
        assert mock_send.call_count == 1
        kwargs = mock_send.call_args.kwargs
        assert kwargs["org_id"] == org.id
        assert kwargs["customer_email"] == "a@test.com"
        assert kwargs["subject"] == campaign.subject
        assert kwargs["body"] == campaign.body
        assert kwargs["product_name"] == "Taskly"
        assert kwargs["template_key"] is None

        db.expire_all()
        updated = db.query(OutreachCampaignRecipient).filter_by(id=recipient.id).first()
        assert updated.status == "sent"
        assert updated.error is None
        assert db.query(OutreachCampaign).filter_by(id=campaign.id).first().status == "done"

    def test_skipped_result_maps_to_skipped_with_reason(self, db, monkeypatch):
        org = _make_org(db)
        campaign = _make_campaign(db, org.id)
        recipient = _make_recipient(db, campaign.id, "a@test.com")
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            return_value={"ok": False, "status": "skipped", "reason": "opted out"},
        ):
            result = _get_tasks().send_outreach_email(campaign.id, recipient.id)

        assert result["status"] == "skipped"
        assert result["error"] == "opted out"
        db.expire_all()
        updated = db.query(OutreachCampaignRecipient).filter_by(id=recipient.id).first()
        assert updated.status == "skipped"
        assert updated.error == "opted out"

    def test_failed_result_maps_to_failed_with_reason(self, db, monkeypatch):
        org = _make_org(db)
        campaign = _make_campaign(db, org.id)
        recipient = _make_recipient(db, campaign.id, "a@test.com")
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            return_value={"ok": False, "status": "failed", "reason": "email not configured"},
        ):
            result = _get_tasks().send_outreach_email(campaign.id, recipient.id)

        assert result["status"] == "failed"
        assert result["error"] == "email not configured"
        db.expire_all()
        updated = db.query(OutreachCampaignRecipient).filter_by(id=recipient.id).first()
        assert updated.status == "failed"
        assert updated.error == "email not configured"

    def test_terminal_recipient_is_a_noop(self, db, monkeypatch):
        org = _make_org(db)
        campaign = _make_campaign(db, org.id)
        recipient = _make_recipient(db, campaign.id, "a@test.com", status="sent")
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            return_value={"ok": True, "status": "sent", "reason": ""},
        ) as mock_send:
            result = _get_tasks().send_outreach_email(campaign.id, recipient.id)

        assert result["status"] == "skipped"
        assert mock_send.call_count == 0
        db.expire_all()
        unchanged = db.query(OutreachCampaignRecipient).filter_by(id=recipient.id).first()
        assert unchanged.status == "sent"

    def test_campaign_done_only_when_all_recipients_terminal(self, db, monkeypatch):
        org = _make_org(db)
        campaign = _make_campaign(db, org.id, recipient_count=2)
        _make_recipient(db, campaign.id, "pending@test.com", status="queued")
        recipient = _make_recipient(db, campaign.id, "a@test.com", status="queued")
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            return_value={"ok": True, "status": "sent", "reason": ""},
        ):
            _get_tasks().send_outreach_email(campaign.id, recipient.id)

        db.expire_all()
        assert db.query(OutreachCampaign).filter_by(id=campaign.id).first().status == "in_progress"

    def test_queued_campaign_flips_to_in_progress_defensively(self, db, monkeypatch):
        org = _make_org(db)
        campaign = _make_campaign(db, org.id, status="queued", recipient_count=2)
        _make_recipient(db, campaign.id, "pending@test.com", status="queued")
        recipient = _make_recipient(db, campaign.id, "a@test.com", status="queued")
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            return_value={"ok": True, "status": "sent", "reason": ""},
        ):
            _get_tasks().send_outreach_email(campaign.id, recipient.id)

        db.expire_all()
        assert db.query(OutreachCampaign).filter_by(id=campaign.id).first().status == "in_progress"

    def test_missing_recipient_returns_error_dict(self, db, monkeypatch):
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            return_value={"ok": True, "status": "sent", "reason": ""},
        ) as mock_send:
            result = _get_tasks().send_outreach_email(campaign_id=999, recipient_id=999)

        assert result["status"] == "error"
        assert "recipient not found" in result["error"]
        assert mock_send.call_count == 0

    def test_missing_campaign_marks_recipient_failed(self, db, monkeypatch):
        org = _make_org(db)
        orphan = _make_recipient(db, campaign_id=999, email="a@test.com")
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            return_value={"ok": True, "status": "sent", "reason": ""},
        ) as mock_send:
            result = _get_tasks().send_outreach_email(campaign_id=999, recipient_id=orphan.id)

        assert result["status"] == "error"
        assert mock_send.call_count == 0
        db.expire_all()
        updated = db.query(OutreachCampaignRecipient).filter_by(id=orphan.id).first()
        assert updated.status == "failed"

    def test_exception_marks_recipient_failed_and_does_not_raise(self, db, monkeypatch):
        org = _make_org(db)
        campaign = _make_campaign(db, org.id)
        recipient = _make_recipient(db, campaign.id, "a@test.com")
        self._patch_db_session(monkeypatch, db)

        with patch(
            "src.services.outreach_sender.send_outreach_email",
            side_effect=RuntimeError("boom"),
        ):
            result = _get_tasks().send_outreach_email(campaign.id, recipient.id)

        assert result["status"] == "error"
        assert "boom" in result["error"]
        db.expire_all()
        updated = db.query(OutreachCampaignRecipient).filter_by(id=recipient.id).first()
        assert updated.status == "failed"
        assert "boom" in (updated.error or "")
