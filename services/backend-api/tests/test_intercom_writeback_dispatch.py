"""
Seam tests for the intercom write-back dispatch (dispatch-seams aspect, R6).

Strict TDD: written FIRST (RED) — no dispatch exists yet.

Every backend writer that can move an Intercom-sourced item to `resolved`
must enqueue the write-back task:

  1. POST /api/v1/workflow/status                 (internal bulk route)
  2. POST /api/public/v1/feedback/bulk            (public API bulk)
  3. PATCH /api/public/v1/feedback/{id}           (public API single)

Each seam test asserts the EXACT send_task args (dotted name + payload),
and the helper negatives assert the R2 guards: non-Intercom source,
non-resolved status, and same-value no-ops never dispatch. The never-raise
tests pin AC2 (a broker failure or an unimportable celery client must not
fail the request).

Pattern: tests/test_health_writeback_enqueue.py (mock get_celery_app, assert
send_task args). Route patterns: tests/test_workflow_status.py (internal
route) and tests/test_public_api_bulk_feedback.py / test_public_api_write.py
(API-key routes).
"""
import hashlib
import secrets
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from src.models.api_key import ApiKey
from src.models.feedback import FeedbackItem
from src.models.organization import Organization

DISPATCH_STRING = "src.tasks.intercom_writeback.push_resolved_writeback"
GET_CELERY_TARGET = "src.background.celery_client.get_celery_app"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feedback(
    db: Session, org: Organization, source: str = "intercom", status: str = "new"
) -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org.id,
        customer_email="customer@example.com",
        text="Intercom-sourced complaint about billing.",
        source=source,
        sentiment_label="negative",
        sentiment_score=-0.7,
        is_urgent=False,
        workflow_status=status,
        created_at=datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _make_api_key(db: Session, org_id: int, scopes: str = "write") -> tuple[str, ApiKey]:
    raw = f"rrf_{secrets.token_urlsafe(24)}"
    prefix = raw[:10]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = ApiKey(
        organization_id=org_id,
        name="intercom writeback test key",
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes,
        revoked_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


# ---------------------------------------------------------------------------
# Seam test 1 — POST /api/v1/workflow/status (internal route)
# ---------------------------------------------------------------------------


class TestInternalRouteDispatch:
    def test_resolved_intercom_item_dispatches(self, client, auth_headers, db, test_organization, test_user):
        fb = _make_feedback(db, test_organization, source="intercom", status="new")

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            response = client.post(
                "/api/v1/workflow/status",
                json={
                    "feedback_ids": [fb.id],
                    "new_status": "resolved",
                    "resolution_note": "fixed the billing bug",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_celery.send_task.assert_called_once_with(
            DISPATCH_STRING,
            args=[test_organization.id, [{"id": fb.id, "resolution_note": "fixed the billing bug"}]],
        )

    def test_non_intercom_item_does_not_dispatch(self, client, auth_headers, db, test_organization, test_user):
        fb = _make_feedback(db, test_organization, source="email", status="new")

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            response = client.post(
                "/api/v1/workflow/status",
                json={"feedback_ids": [fb.id], "new_status": "resolved"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_celery.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# Seam test 2 — POST /api/public/v1/feedback/bulk (public API)
# ---------------------------------------------------------------------------


class TestPublicBulkDispatch:
    def test_resolved_intercom_item_dispatches(self, client, db, test_organization):
        raw, _ = _make_api_key(db, test_organization.id, scopes="write")
        fb = _make_feedback(db, test_organization, source="intercom", status="new")

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            response = client.post(
                "/api/public/v1/feedback/bulk",
                json={
                    "ids": [fb.id],
                    "patch": {
                        "workflow_status": "resolved",
                        "resolution_note": "fixed via public API",
                    },
                },
                headers={"X-API-Key": raw},
            )

        assert response.status_code == 200
        mock_celery.send_task.assert_called_once_with(
            DISPATCH_STRING,
            args=[test_organization.id, [{"id": fb.id, "resolution_note": "fixed via public API"}]],
        )


# ---------------------------------------------------------------------------
# Seam test 3 — PATCH /api/public/v1/feedback/{id} (public API single)
# ---------------------------------------------------------------------------


class TestPublicSingleDispatch:
    def test_resolved_intercom_item_dispatches(self, client, db, test_organization):
        raw, _ = _make_api_key(db, test_organization.id, scopes="write")
        fb = _make_feedback(db, test_organization, source="intercom", status="new")

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            response = client.patch(
                f"/api/public/v1/feedback/{fb.id}",
                json={
                    "workflow_status": "resolved",
                    "resolution_note": "fixed via public API",
                },
                headers={"X-API-Key": raw},
            )

        assert response.status_code == 200
        mock_celery.send_task.assert_called_once_with(
            DISPATCH_STRING,
            args=[test_organization.id, [{"id": fb.id, "resolution_note": "fixed via public API"}]],
        )


# ---------------------------------------------------------------------------
# Helper negatives — direct calls to dispatch_intercom_writeback
# ---------------------------------------------------------------------------


class TestHelperNegatives:
    def test_non_intercom_source_does_not_dispatch(self, db, test_organization):
        fb = _make_feedback(db, test_organization, source="email", status="resolved")

        from src.services.workflow_service import dispatch_intercom_writeback
        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            dispatch_intercom_writeback(
                db, test_organization.id, [(fb, "new")], "note"
            )

        mock_celery.send_task.assert_not_called()

    def test_non_resolved_status_does_not_dispatch(self, db, test_organization):
        fb = _make_feedback(db, test_organization, source="intercom", status="in_review")

        from src.services.workflow_service import dispatch_intercom_writeback
        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            dispatch_intercom_writeback(
                db, test_organization.id, [(fb, "new")], "note"
            )

        mock_celery.send_task.assert_not_called()

    def test_same_value_noop_empty_changed_pairs_does_not_dispatch(self, db, test_organization):
        from src.services.workflow_service import dispatch_intercom_writeback
        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            dispatch_intercom_writeback(db, test_organization.id, [], "note")

        mock_celery.send_task.assert_not_called()
        mock_get_celery.assert_not_called()

    def test_mixed_batch_payload_contains_only_intercom_items(self, db, test_organization):
        fb_intercom = _make_feedback(db, test_organization, source="intercom", status="resolved")
        fb_email = _make_feedback(db, test_organization, source="email", status="resolved")

        from src.services.workflow_service import dispatch_intercom_writeback
        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            dispatch_intercom_writeback(
                db,
                test_organization.id,
                [(fb_intercom, "new"), (fb_email, "new")],
                "note",
            )

        mock_celery.send_task.assert_called_once_with(
            DISPATCH_STRING,
            args=[test_organization.id, [{"id": fb_intercom.id, "resolution_note": "note"}]],
        )

    def test_resolution_note_none_serializes_null(self, db, test_organization):
        fb = _make_feedback(db, test_organization, source="intercom", status="resolved")

        from src.services.workflow_service import dispatch_intercom_writeback
        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            dispatch_intercom_writeback(
                db, test_organization.id, [(fb, "new")], None
            )

        mock_celery.send_task.assert_called_once_with(
            DISPATCH_STRING,
            args=[test_organization.id, [{"id": fb.id, "resolution_note": None}]],
        )


# ---------------------------------------------------------------------------
# AC2 — never raises (send_task failure / unimportable celery client)
# ---------------------------------------------------------------------------


class TestNeverRaises:
    def test_send_task_failure_does_not_raise(self, db, test_organization):
        fb = _make_feedback(db, test_organization, source="intercom", status="resolved")

        from src.services.workflow_service import dispatch_intercom_writeback
        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_celery.send_task.side_effect = RuntimeError("broker down")
            mock_get_celery.return_value = mock_celery

            dispatch_intercom_writeback(
                db, test_organization.id, [(fb, "new")], "note"
            )

    def test_get_celery_app_import_error_does_not_raise(self, db, test_organization):
        fb = _make_feedback(db, test_organization, source="intercom", status="resolved")

        with patch(GET_CELERY_TARGET, side_effect=ImportError("no celery client here")):
            dispatch_intercom_writeback(
                db, test_organization.id, [(fb, "new")], "note"
            )
