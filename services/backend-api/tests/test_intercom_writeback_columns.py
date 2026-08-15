"""
TDD ORM-level tests for intercom-writeback (db-config-model aspect, R1 + R4).

Default-deny (spec AC2): a freshly-built IntercomIntegration is
writeback_enabled=False with action "note_and_close"; the per-feedback marker
intercom_writeback_at is NULL until a writeback happens.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.intercom_integration import IntercomIntegration
from src.models.organization import Organization


def _make_integration(db: Session, org_id: int) -> IntercomIntegration:
    row = IntercomIntegration(
        organization_id=org_id,
        access_token="enc:token",
        workspace_id="ws_acme",
        connected_at=datetime.utcnow(),
    )
    db.add(row)
    return row


def test_intercom_integration_defaults_off_and_note_and_close(
    db: Session, test_organization: Organization
):
    row = _make_integration(db, test_organization.id)
    db.commit()
    db.refresh(row)

    assert row.writeback_enabled is False
    assert row.writeback_action == "note_and_close"
    assert row.last_writeback_at is None
    assert row.last_writeback_status is None
    assert row.last_writeback_error is None


def test_intercom_integration_writeback_fields_settable(
    db: Session, test_organization: Organization
):
    written_at = datetime(2026, 8, 15, 12, 0, 0)
    row = _make_integration(db, test_organization.id)
    row.writeback_enabled = True
    row.writeback_action = "note_only"
    row.last_writeback_at = written_at
    row.last_writeback_status = "resolved"
    row.last_writeback_error = None
    db.commit()
    db.refresh(row)

    assert row.writeback_enabled is True
    assert row.writeback_action == "note_only"
    assert row.last_writeback_at == written_at
    assert row.last_writeback_status == "resolved"
    assert row.last_writeback_error is None


def test_feedback_item_intercom_writeback_at_defaults_null(
    db: Session, test_feedback: FeedbackItem
):
    assert test_feedback.intercom_writeback_at is None


def test_feedback_item_marker_settable(db: Session, test_feedback: FeedbackItem):
    written_at = datetime(2026, 8, 15, 13, 30, 0)
    test_feedback.intercom_writeback_at = written_at
    db.commit()
    db.refresh(test_feedback)
    assert test_feedback.intercom_writeback_at == written_at
