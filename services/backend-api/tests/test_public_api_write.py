"""
Tests for the public write endpoint — PATCH /api/public/v1/feedback/{id}.

TDD: RED → GREEN → REFACTOR.

Coverage:
  - write scope required (read/ingest keys → 403)
  - workflow_status change: 200, item mutated, one FeedbackWorkflowEvent with
    actor_id NULL, webhook dispatched with changed_by="api-key:<name>"
  - same-status PATCH → 200 no-op (no event, no webhook)
  - correction: 200, one AICorrection (record-only, category unchanged, user_id NULL)
  - empty body → 400
  - cross-org / non-existent id → 404 (NOT 403)
  - invalid workflow_status → 422 (Literal validation)
  - combined status + correction → both applied

Self-contained in-memory SQLite engine, mirroring tests/test_public_api.py.
"""

import hashlib
import secrets
from datetime import datetime
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.main import app
from src.database.session import get_db
from src.models.ai_correction import AICorrection
from src.models.api_key import ApiKey
from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.integration import Integration, SlackAlertLog
from src.models.organization import Organization
from src.models.base import Base

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── In-memory SQLite engine ───────────────────────────────────────────────────

_SQLITE_URL = "sqlite:///:memory:"
_engine = create_engine(
    _SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=_engine)
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Acme Corp", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def org_b(db: Session) -> Organization:
    o = Organization(name="Rival Inc", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _make_api_key(
    db: Session, org_id: int, scopes: str = "write", name: str = "test key"
) -> tuple[str, ApiKey]:
    raw = f"rrf_{secrets.token_urlsafe(24)}"
    prefix = raw[:10]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = ApiKey(
        organization_id=org_id,
        name=name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes,
        revoked_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def _feedback_in_org(
    db: Session,
    org_id: int,
    text: str = "some feedback",
    workflow_status: str = "new",
    pain_point_category: str = None,
    feature_request_category: str = None,
    sentiment_label: str = None,
    tags: list = None,
    is_urgent: bool = False,
) -> FeedbackItem:
    f = FeedbackItem(
        organization_id=org_id,
        text=text,
        source="test",
        is_urgent=is_urgent,
        workflow_status=workflow_status,
        pain_point_category=pain_point_category,
        feature_request_category=feature_request_category,
        sentiment_label=sentiment_label,
        tags=tags,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ═══════════════════════════════════════════════════════════════════════════════
# § Status change
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicWriteStatus:
    def test_write_key_changes_status(self, client, db, org, monkeypatch):
        """write key + workflow_status=resolved → 200, resolved, one event
        (actor_id NULL), webhook dispatched with changed_by=api-key:<name>."""
        calls = []

        def fake_dispatch(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(
            "src.services.webhook_dispatcher.dispatch_webhook_event", fake_dispatch
        )

        raw, key_row = _make_api_key(db, org.id, scopes="write", name="mykey")
        fb = _feedback_in_org(db, org.id, workflow_status="new")

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"workflow_status": "resolved"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["workflow_status"] == "resolved"

        db.refresh(fb)
        assert fb.workflow_status == "resolved"

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == fb.id)
            .all()
        )
        assert len(events) == 1
        assert events[0].event_type == "status_changed"
        assert events[0].new_value == "resolved"
        assert events[0].actor_id is None

        assert len(calls) == 1
        assert calls[0]["changes"]["changed_by"] == "api-key:mykey"
        assert calls[0]["event_type"] == "feedback.status_changed"

    def test_same_status_is_noop(self, client, db, org, monkeypatch):
        """PATCH to the same status → 200 no-op: no new event, no webhook."""
        calls = []
        monkeypatch.setattr(
            "src.services.webhook_dispatcher.dispatch_webhook_event",
            lambda **kw: calls.append(kw),
        )

        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, workflow_status="resolved")

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"workflow_status": "resolved"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == fb.id)
            .all()
        )
        assert len(events) == 0
        assert len(calls) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# § Correction
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicWriteCorrection:
    def test_correction_records_only(self, client, db, org):
        """correction pain_point → 200, one AICorrection (record-only);
        stored category unchanged; user_id NULL."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, pain_point_category="performance")

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"correction": {"field": "pain_point", "corrected_value": "billing"}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text

        corrections = (
            db.query(AICorrection)
            .filter(AICorrection.entity_id == fb.id)
            .all()
        )
        assert len(corrections) == 1
        c = corrections[0]
        assert c.signal == "correction"
        assert c.correction_type == "category"
        assert c.original_value == "performance"
        assert c.corrected_value == "billing"
        assert c.user_id is None

        db.refresh(fb)
        assert fb.pain_point_category == "performance"  # unchanged


# ═══════════════════════════════════════════════════════════════════════════════
# § Validation & auth
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicWriteValidation:
    def test_empty_body_400(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)
        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 400, resp.text

    def test_read_key_forbidden(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        fb = _feedback_in_org(db, org.id)
        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"workflow_status": "resolved"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_ingest_key_forbidden(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read,ingest")
        fb = _feedback_in_org(db, org.id)
        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"workflow_status": "resolved"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_cross_org_404(self, client, db, org, org_b):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb_b = _feedback_in_org(db, org_b.id)
        resp = client.patch(
            f"/api/public/v1/feedback/{fb_b.id}",
            json={"workflow_status": "resolved"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404, resp.text
        # cross-org must NOT leak via 403
        assert resp.status_code != 403

    def test_nonexistent_404(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        resp = client.patch(
            "/api/public/v1/feedback/999999",
            json={"workflow_status": "resolved"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404, resp.text

    def test_invalid_status_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)
        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"workflow_status": "done"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 422, resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# § Combined
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicWriteCombined:
    def test_status_and_correction_both_applied(self, client, db, org, monkeypatch):
        monkeypatch.setattr(
            "src.services.webhook_dispatcher.dispatch_webhook_event",
            lambda **kw: None,
        )
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(
            db, org.id, workflow_status="new", sentiment_label="neutral"
        )

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={
                "workflow_status": "in_review",
                "correction": {"field": "sentiment", "corrected_value": "negative"},
            },
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text

        db.refresh(fb)
        assert fb.workflow_status == "in_review"
        assert fb.sentiment_label == "neutral"  # correction is record-only

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == fb.id)
            .all()
        )
        assert len(events) == 1

        corrections = (
            db.query(AICorrection).filter(AICorrection.entity_id == fb.id).all()
        )
        assert len(corrections) == 1
        assert corrections[0].correction_type == "sentiment"
        assert corrections[0].original_value == "neutral"
        assert corrections[0].corrected_value == "negative"


# ═══════════════════════════════════════════════════════════════════════════════
# § Tags
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicWriteTags:
    def test_tags_trim_and_persist(self, client, db, org):
        """tags with whitespace persist trimmed; case-sensitive distinct values kept."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["Bug", " bug ", "perf"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tags"] == ["Bug", "bug", "perf"]

        # Re-fetch via a fresh query to prove JSON persistence (not just in-memory).
        refetched = db.query(FeedbackItem).filter(FeedbackItem.id == fb.id).first()
        assert refetched.tags == ["Bug", "bug", "perf"]

    def test_tags_empty_list_clears(self, client, db, org):
        """tags: [] clears existing tags."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, tags=["existing", "tags"])

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": []},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tags"] == []

        refetched = db.query(FeedbackItem).filter(FeedbackItem.id == fb.id).first()
        assert refetched.tags == []

    def test_tags_omitted_unchanged(self, client, db, org):
        """PATCH without tags key (only is_urgent) leaves existing tags untouched."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, tags=["existing", "tags"])

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"is_urgent": True},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tags"] == ["existing", "tags"]

        refetched = db.query(FeedbackItem).filter(FeedbackItem.id == fb.id).first()
        assert refetched.tags == ["existing", "tags"]

    def test_tags_dedupe(self, client, db, org):
        """Duplicate tags collapse to first-seen order."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["a", "a"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tags"] == ["a"]

    def test_tags_too_many_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": [f"t{i}" for i in range(21)]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 422, resp.text

    def test_tags_element_too_long_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["x" * 51]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 422, resp.text

    def test_tags_non_string_element_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["a", 3]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 422, resp.text

    def test_tags_empty_string_element_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["a", ""]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 422, resp.text

    def test_tags_only_200_guard_widened(self, client, db, org):
        """PATCH with only tags → 200 (guard widened, not the old 400)."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["x"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tags"] == ["x"]

    def test_tags_unknown_field_422(self, client, db, org):
        """Unknown field (typo `tag`) → 422 via extra='forbid'."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tag": ["x"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 422, resp.text

    def test_tags_read_key_forbidden(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        fb = _feedback_in_org(db, org.id)
        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["x"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_tags_ingest_key_forbidden(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read,ingest")
        fb = _feedback_in_org(db, org.id)
        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["x"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_tags_cross_org_404(self, client, db, org, org_b):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb_b = _feedback_in_org(db, org_b.id)
        resp = client.patch(
            f"/api/public/v1/feedback/{fb_b.id}",
            json={"tags": ["x"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404, resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# § is_urgent
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicWriteUrgent:
    def test_is_urgent_true(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, is_urgent=False)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"is_urgent": True},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_urgent"] is True

        refetched = db.query(FeedbackItem).filter(FeedbackItem.id == fb.id).first()
        assert refetched.is_urgent is True

    def test_is_urgent_false(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, is_urgent=True)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"is_urgent": False},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_urgent"] is False

        refetched = db.query(FeedbackItem).filter(FeedbackItem.id == fb.id).first()
        assert refetched.is_urgent is False

    def test_is_urgent_omitted_unchanged(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, is_urgent=True)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={"tags": ["x"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_urgent"] is True

        refetched = db.query(FeedbackItem).filter(FeedbackItem.id == fb.id).first()
        assert refetched.is_urgent is True


# ═══════════════════════════════════════════════════════════════════════════════
# § Combined tags + is_urgent + status
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicWriteFieldsCombined:
    def test_status_tags_urgent_all_applied(self, client, db, org, monkeypatch):
        monkeypatch.setattr(
            "src.services.webhook_dispatcher.dispatch_webhook_event",
            lambda **kw: None,
        )
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, workflow_status="new", is_urgent=False)

        resp = client.patch(
            f"/api/public/v1/feedback/{fb.id}",
            json={
                "workflow_status": "resolved",
                "tags": ["x"],
                "is_urgent": True,
            },
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workflow_status"] == "resolved"
        assert body["tags"] == ["x"]
        assert body["is_urgent"] is True

        refetched = db.query(FeedbackItem).filter(FeedbackItem.id == fb.id).first()
        assert refetched.workflow_status == "resolved"
        assert refetched.tags == ["x"]
        assert refetched.is_urgent is True


# ═══════════════════════════════════════════════════════════════════════════════
# § Delete — DELETE /api/public/v1/feedback/{id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicDeleteFeedback:
    def test_write_key_deletes_204_row_gone(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.delete(
            f"/api/public/v1/feedback/{fb.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 204, resp.text

        assert db.query(FeedbackItem).filter(FeedbackItem.id == fb.id).first() is None

    def test_nonexistent_404(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")

        resp = client.delete(
            "/api/public/v1/feedback/999999",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404, resp.text

    def test_cross_org_404(self, client, db, org, org_b):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb_b = _feedback_in_org(db, org_b.id)

        resp = client.delete(
            f"/api/public/v1/feedback/{fb_b.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404, resp.text
        assert resp.status_code != 403

        # row must still exist in org_b — no tenant leak
        assert db.query(FeedbackItem).filter(FeedbackItem.id == fb_b.id).first() is not None

    def test_read_key_forbidden(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        fb = _feedback_in_org(db, org.id)

        resp = client.delete(
            f"/api/public/v1/feedback/{fb.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_ingest_key_forbidden(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read,ingest")
        fb = _feedback_in_org(db, org.id)

        resp = client.delete(
            f"/api/public/v1/feedback/{fb.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_write_only_key_no_read_scope_can_delete(self, client, db, org):
        """A write-only key (no read scope) must still be able to delete."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.delete(
            f"/api/public/v1/feedback/{fb.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 204, resp.text

    def test_delete_last_feedback_archives_customer_health(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, text="last one")
        fb.customer_email = "churner@example.com"
        db.commit()

        health = CustomerHealth(
            organization_id=org.id,
            customer_email="churner@example.com",
            is_archived=False,
        )
        db.add(health)
        db.commit()

        resp = client.delete(
            f"/api/public/v1/feedback/{fb.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 204, resp.text

        db.refresh(health)
        assert health.is_archived is True

    def test_delete_non_last_feedback_does_not_archive(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb1 = _feedback_in_org(db, org.id, text="one")
        fb2 = _feedback_in_org(db, org.id, text="two")
        fb1.customer_email = "loyal@example.com"
        fb2.customer_email = "loyal@example.com"
        db.commit()

        health = CustomerHealth(
            organization_id=org.id,
            customer_email="loyal@example.com",
            is_archived=False,
        )
        db.add(health)
        db.commit()

        resp = client.delete(
            f"/api/public/v1/feedback/{fb1.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 204, resp.text

        db.refresh(health)
        assert health.is_archived is False

    def test_delete_with_slack_alert_log_reference_no_fk_error(self, client, db, org):
        """Deleting an item referenced by a SlackAlertLog must not raise an FK error
        (mirrors the internal single-delete, which does not null the reference)."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        integration = Integration(organization_id=org.id, type="slack", name="eng")
        db.add(integration)
        db.commit()
        db.refresh(integration)

        alert = SlackAlertLog(
            integration_id=integration.id,
            feedback_id=fb.id,
            alert_type="urgent",
            status="sent",
        )
        db.add(alert)
        db.commit()

        resp = client.delete(
            f"/api/public/v1/feedback/{fb.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 204, resp.text
