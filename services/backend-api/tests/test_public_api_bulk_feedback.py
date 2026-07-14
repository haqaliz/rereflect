"""
Tests for the public bulk-write endpoint — POST /api/public/v1/feedback/bulk.

TDD: RED -> GREEN -> REFACTOR. See
docs/planning/public-api-crud-v3/bulk-feedback-write/plan_20260714.md for the
full spec this suite locks down.

Coverage (added phase by phase):
  - schema validation (Phase 2)
  - happy path: batched status + per-item results (Phase 3)
  - edge cases: scope/skipped/noop/dedupe/cap/non-contagion (Phase 4)
  - count_only dry-run (Phase 5)

Self-contained in-memory SQLite engine, mirroring tests/test_public_api_write.py.
"""

import hashlib
import secrets
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.session import get_db
from src.models.ai_correction import AICorrection
from src.models.api_key import ApiKey
from src.models.base import Base
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.organization import Organization

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
# § Phase 2 — schema validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestBulkUpdateSchema:
    def test_empty_ids_rejected(self):
        from src.api.routes.public_api import PublicFeedbackBulkUpdate

        with pytest.raises(ValidationError):
            PublicFeedbackBulkUpdate(ids=[], patch={"workflow_status": "resolved"})

    def test_over_cap_ids_rejected(self):
        from src.api.routes.public_api import PublicFeedbackBulkUpdate

        with pytest.raises(ValidationError):
            PublicFeedbackBulkUpdate(
                ids=list(range(1, 502)), patch={"workflow_status": "resolved"}
            )

    def test_501_is_over_cap_but_500_is_ok(self):
        from src.api.routes.public_api import PublicFeedbackBulkUpdate

        # 500 must be accepted (boundary)
        PublicFeedbackBulkUpdate(
            ids=list(range(1, 501)), patch={"workflow_status": "resolved"}
        )
        with pytest.raises(ValidationError):
            PublicFeedbackBulkUpdate(
                ids=list(range(1, 502)), patch={"workflow_status": "resolved"}
            )

    def test_unknown_top_level_field_rejected(self):
        from src.api.routes.public_api import PublicFeedbackBulkUpdate

        with pytest.raises(ValidationError):
            PublicFeedbackBulkUpdate(
                ids=[1],
                patch={"workflow_status": "resolved"},
                bogus_field="nope",
            )

    def test_patch_bad_tag_length_rejected(self):
        from src.api.routes.public_api import PublicFeedbackBulkUpdate

        with pytest.raises(ValidationError):
            PublicFeedbackBulkUpdate(ids=[1], patch={"tags": ["x" * 51]})

    def test_valid_schema_constructs(self):
        from src.api.routes.public_api import PublicFeedbackBulkUpdate

        model = PublicFeedbackBulkUpdate(
            ids=[1, 2, 3], patch={"workflow_status": "resolved", "is_urgent": True}
        )
        assert model.ids == [1, 2, 3]
        assert model.patch.workflow_status == "resolved"

    def test_result_item_status_literal(self):
        from src.api.routes.public_api import PublicFeedbackBulkResultItem

        item = PublicFeedbackBulkResultItem(id=1, status="updated")
        assert item.status == "updated"
        with pytest.raises(ValidationError):
            PublicFeedbackBulkResultItem(id=1, status="bogus")

    def test_response_shape(self):
        from src.api.routes.public_api import (
            PublicFeedbackBulkResponse,
            PublicFeedbackBulkResultItem,
        )

        resp = PublicFeedbackBulkResponse(
            matched=2,
            updated=1,
            skipped=1,
            results=[
                PublicFeedbackBulkResultItem(id=1, status="updated"),
                PublicFeedbackBulkResultItem(id=2, status="skipped", reason="not_found"),
            ],
        )
        assert resp.matched == 2
        assert resp.updated == 1
        assert resp.skipped == 1
        assert len(resp.results) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# § Phase 3 — happy path
# ═══════════════════════════════════════════════════════════════════════════════


class TestBulkUpdateHappyPath:
    def test_three_valid_ids_status_and_urgent(self, client, db, org, monkeypatch):
        webhook_calls = []
        monkeypatch.setattr(
            "src.services.webhook_dispatcher.dispatch_webhook_event",
            lambda **kw: webhook_calls.append(kw),
        )

        raw, _ = _make_api_key(db, org.id, scopes="write")
        fbs = [_feedback_in_org(db, org.id, workflow_status="new") for _ in range(3)]
        ids = [fb.id for fb in fbs]

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={
                "ids": ids,
                "patch": {"workflow_status": "resolved", "is_urgent": True},
            },
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["matched"] == 3
        assert body["updated"] == 3
        assert body["skipped"] == 0
        assert len(body["results"]) == 3
        for r in body["results"]:
            assert r["status"] == "updated"
            assert r["id"] in ids

        for fb in fbs:
            db.refresh(fb)
            assert fb.workflow_status == "resolved"
            assert fb.is_urgent is True

        # one webhook per changed item
        assert len(webhook_calls) == 3

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id.in_(ids))
            .all()
        )
        assert len(events) == 3
        for e in events:
            assert e.event_type == "status_changed"
            assert e.new_value == "resolved"


# ═══════════════════════════════════════════════════════════════════════════════
# § Phase 4 — edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestBulkUpdateScope:
    def test_read_key_forbidden(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        fb = _feedback_in_org(db, org.id)
        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={"ids": [fb.id], "patch": {"workflow_status": "resolved"}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_bad_key_401(self, client, db, org):
        fb = _feedback_in_org(db, org.id)
        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={"ids": [fb.id], "patch": {"workflow_status": "resolved"}},
            headers={"Authorization": "Bearer rrf_totally_bogus_key"},
        )
        assert resp.status_code == 401, resp.text


class TestBulkUpdateCrossOrgAndPartial:
    def test_cross_org_id_skipped_not_counted(self, client, db, org, org_b):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb_own = _feedback_in_org(db, org.id, workflow_status="new")
        fb_other = _feedback_in_org(db, org_b.id, workflow_status="new")

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={
                "ids": [fb_own.id, fb_other.id],
                "patch": {"workflow_status": "resolved"},
            },
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["matched"] == 1
        assert body["updated"] == 1
        assert body["skipped"] == 1
        results_by_id = {r["id"]: r for r in body["results"]}
        assert results_by_id[fb_own.id]["status"] == "updated"
        assert results_by_id[fb_other.id]["status"] == "skipped"
        assert results_by_id[fb_other.id]["reason"] == "not_found"

        db.refresh(fb_own)
        assert fb_own.workflow_status == "resolved"
        db.refresh(fb_other)
        assert fb_other.workflow_status == "new"  # untouched

    def test_good_good_bad_matched_2_updated_2_skipped_1(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb1 = _feedback_in_org(db, org.id, workflow_status="new")
        fb2 = _feedback_in_org(db, org.id, workflow_status="new")
        bad_id = 999999

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={
                "ids": [fb1.id, fb2.id, bad_id],
                "patch": {"workflow_status": "resolved"},
            },
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["matched"] == 2
        assert body["updated"] == 2
        assert body["skipped"] == 1
        assert len(body["results"]) == 3

        db.refresh(fb1)
        db.refresh(fb2)
        assert fb1.workflow_status == "resolved"
        assert fb2.workflow_status == "resolved"


class TestBulkUpdateNoop:
    def test_same_status_no_other_field_is_noop(self, client, db, org, monkeypatch):
        webhook_calls = []
        monkeypatch.setattr(
            "src.services.webhook_dispatcher.dispatch_webhook_event",
            lambda **kw: webhook_calls.append(kw),
        )
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, workflow_status="resolved")

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={"ids": [fb.id], "patch": {"workflow_status": "resolved"}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["matched"] == 1
        assert body["updated"] == 0
        assert body["results"][0]["status"] == "noop"
        assert len(webhook_calls) == 0

        events = (
            db.query(FeedbackWorkflowEvent)
            .filter(FeedbackWorkflowEvent.feedback_id == fb.id)
            .all()
        )
        assert len(events) == 0


class TestBulkUpdateDedupe:
    def test_duplicate_ids_deduped_one_result(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, workflow_status="new")

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={
                "ids": [fb.id, fb.id, fb.id],
                "patch": {"workflow_status": "resolved"},
            },
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["matched"] == 1
        assert body["updated"] == 1
        assert len(body["results"]) == 1


class TestBulkUpdateCap:
    def test_501_ids_422_nothing_mutated(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id, workflow_status="new")
        ids = [fb.id] + list(range(100000, 100000 + 500))  # 501 total

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={"ids": ids, "patch": {"workflow_status": "resolved"}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 422, resp.text

        db.refresh(fb)
        assert fb.workflow_status == "new"  # untouched


class TestBulkUpdateEmptyPatch:
    def test_empty_patch_400(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={"ids": [fb.id], "patch": {}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 400, resp.text

    def test_only_resolution_note_400(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb = _feedback_in_org(db, org.id)

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={"ids": [fb.id], "patch": {"resolution_note": "fyi only"}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 400, resp.text


class TestBulkUpdateNonContagion:
    def test_one_item_error_others_persist(self, client, db, org, monkeypatch):
        """Force a per-item error via create_ai_correction raising for one id.
        That id -> error; others -> updated and persisted; savepoint rollback
        only affects the failing item."""
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb_ok1 = _feedback_in_org(db, org.id, workflow_status="new", is_urgent=False)
        fb_bad = _feedback_in_org(db, org.id, workflow_status="new", is_urgent=False)
        fb_ok2 = _feedback_in_org(db, org.id, workflow_status="new", is_urgent=False)

        real_create_ai_correction = None
        import src.services.ai_correction_service as ai_correction_service

        real_create_ai_correction = ai_correction_service.create_ai_correction

        def flaky_create_ai_correction(db_, *, entity_id=None, **kwargs):
            if entity_id == fb_bad.id:
                raise RuntimeError("simulated per-item failure")
            return real_create_ai_correction(db_, entity_id=entity_id, **kwargs)

        monkeypatch.setattr(
            "src.services.ai_correction_service.create_ai_correction",
            flaky_create_ai_correction,
        )

        resp = client.post(
            "/api/public/v1/feedback/bulk",
            json={
                "ids": [fb_ok1.id, fb_bad.id, fb_ok2.id],
                "patch": {
                    "is_urgent": True,
                    "correction": {"field": "sentiment", "corrected_value": "negative"},
                },
            },
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        results_by_id = {r["id"]: r for r in body["results"]}
        assert results_by_id[fb_ok1.id]["status"] == "updated"
        assert results_by_id[fb_ok2.id]["status"] == "updated"
        assert results_by_id[fb_bad.id]["status"] == "error"

        db.refresh(fb_ok1)
        db.refresh(fb_ok2)
        db.refresh(fb_bad)
        assert fb_ok1.is_urgent is True
        assert fb_ok2.is_urgent is True
        # the failing item's is_urgent change must be rolled back (savepoint)
        assert fb_bad.is_urgent is False

        corrections = (
            db.query(AICorrection)
            .filter(AICorrection.entity_id.in_([fb_ok1.id, fb_ok2.id, fb_bad.id]))
            .all()
        )
        corrected_ids = {c.entity_id for c in corrections}
        assert fb_ok1.id in corrected_ids
        assert fb_ok2.id in corrected_ids
        assert fb_bad.id not in corrected_ids


# ═══════════════════════════════════════════════════════════════════════════════
# § Phase 5 — count_only dry-run
# ═══════════════════════════════════════════════════════════════════════════════


class TestBulkUpdateCountOnly:
    def test_count_only_returns_matched_mutates_nothing(self, client, db, org, monkeypatch):
        webhook_calls = []
        monkeypatch.setattr(
            "src.services.webhook_dispatcher.dispatch_webhook_event",
            lambda **kw: webhook_calls.append(kw),
        )
        raw, _ = _make_api_key(db, org.id, scopes="write")
        fb1 = _feedback_in_org(db, org.id, workflow_status="new")
        fb2 = _feedback_in_org(db, org.id, workflow_status="new")

        resp = client.post(
            "/api/public/v1/feedback/bulk?count_only=true",
            json={"ids": [fb1.id, fb2.id], "patch": {"workflow_status": "resolved"}},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["matched"] == 2
        assert body.get("updated", 0) == 0
        assert not body.get("results")

        db.refresh(fb1)
        db.refresh(fb2)
        assert fb1.workflow_status == "new"
        assert fb2.workflow_status == "new"
        assert len(webhook_calls) == 0

        events = db.query(FeedbackWorkflowEvent).all()
        assert len(events) == 0
