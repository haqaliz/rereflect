"""
Tests for Feature C — Public REST API (PRD §6).

TDD: RED → GREEN → REFACTOR.

Coverage:
  - API key management (create / list / revoke) via JWT auth
  - verify_api_key dependency (valid, revoked, unknown, scope enforcement)
  - Public read endpoints scoped to the key's org (cross-tenant isolation)
  - Ingest endpoint enqueues analysis
  - Scope enforcement (read-only key → 403 on ingest)
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
from src.models.api_key import ApiKey
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import create_access_token, hash_password
from src.models.base import Base

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── In-memory SQLite engine (separate from conftest to ensure isolation) ──────

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


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Acme Corp", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def org_b(db: Session) -> Organization:
    """Second org — used for cross-tenant isolation tests."""
    o = Organization(name="Rival Inc", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def owner_user(db: Session, org: Organization) -> User:
    u = User(
        email="owner@acme.com",
        password_hash=hash_password("secret"),
        organization_id=org.id,
        role="owner",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def member_user(db: Session, org: Organization) -> User:
    u = User(
        email="member@acme.com",
        password_hash=hash_password("secret"),
        organization_id=org.id,
        role="member",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def owner_token(owner_user: User) -> str:
    return create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })


@pytest.fixture
def member_token(member_user: User) -> str:
    return create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })


@pytest.fixture
def owner_headers(owner_token: str) -> dict:
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture
def member_headers(member_token: str) -> dict:
    return {"Authorization": f"Bearer {member_token}"}


def _make_api_key(db: Session, org_id: int, scopes: str = "read", revoked: bool = False) -> tuple[str, ApiKey]:
    """Helper: create a stored ApiKey and return (full_key, orm_row)."""
    raw = f"rrf_{secrets.token_urlsafe(24)}"
    prefix = raw[:10]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = ApiKey(
        organization_id=org_id,
        name="test key",
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes,
        revoked_at=datetime.utcnow() if revoked else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def _feedback_in_org(db: Session, org_id: int, text: str = "some feedback") -> FeedbackItem:
    f = FeedbackItem(organization_id=org_id, text=text, source="test", is_urgent=False)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ═══════════════════════════════════════════════════════════════════════════════
# § Key Management — POST /api/v1/api-keys
# ═══════════════════════════════════════════════════════════════════════════════

class TestApiKeyCreate:
    def test_create_returns_full_key_once(self, client: TestClient, owner_headers: dict, db: Session, org: Organization):
        """Full key is returned exactly once in the response body."""
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "my key", "scopes": ["read"]},
            headers=owner_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "key" in data, "full key must be present in create response"
        assert data["key"].startswith("rrf_"), "key must start with rrf_"

    def test_create_stores_hash_not_key(self, client: TestClient, owner_headers: dict, db: Session, org: Organization):
        """After creation, the DB row stores hash + prefix — not the raw key."""
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "hash check", "scopes": ["read"]},
            headers=owner_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        full_key = data["key"]

        row = db.query(ApiKey).filter(ApiKey.organization_id == org.id).first()
        assert row is not None
        expected_hash = hashlib.sha256(full_key.encode()).hexdigest()
        assert row.key_hash == expected_hash, "stored hash must be sha256 of the full key"
        # The raw key must NOT be stored anywhere on the row
        assert full_key not in (row.key_prefix or "")

    def test_create_stores_prefix(self, client: TestClient, owner_headers: dict, db: Session, org: Organization):
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "prefix check", "scopes": ["read"]},
            headers=owner_headers,
        )
        assert resp.status_code == 201, resp.text
        full_key = resp.json()["key"]
        row = db.query(ApiKey).filter(ApiKey.organization_id == org.id).first()
        assert row is not None
        assert full_key.startswith(row.key_prefix)

    def test_create_with_ingest_scope(self, client: TestClient, owner_headers: dict, db: Session, org: Organization):
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "ingest key", "scopes": ["read", "ingest"]},
            headers=owner_headers,
        )
        assert resp.status_code == 201, resp.text
        row = db.query(ApiKey).filter(ApiKey.organization_id == org.id).first()
        assert "ingest" in row.scopes

    def test_member_cannot_create_key(self, client: TestClient, member_headers: dict):
        """Member role must be rejected (requires admin/owner)."""
        resp = client.post(
            "/api/v1/api-keys",
            json={"name": "bad", "scopes": ["read"]},
            headers=member_headers,
        )
        assert resp.status_code == 403, resp.text

    def test_unauthenticated_cannot_create_key(self, client: TestClient):
        resp = client.post("/api/v1/api-keys", json={"name": "x", "scopes": ["read"]})
        assert resp.status_code in (401, 403), resp.text


class TestApiKeyList:
    def test_list_never_exposes_raw_key(self, client: TestClient, owner_headers: dict, db: Session, org: Organization):
        """GET /api/v1/api-keys must not return key_hash or the raw key."""
        _make_api_key(db, org.id, scopes="read")
        resp = client.get("/api/v1/api-keys", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert isinstance(items, list)
        for item in items:
            assert "key_hash" not in item, "key_hash must never appear in list response"
            assert "key" not in item, "raw key must never appear in list response"

    def test_list_shows_prefix_and_scopes(self, client: TestClient, owner_headers: dict, db: Session, org: Organization):
        raw, row = _make_api_key(db, org.id, scopes="read,ingest")
        resp = client.get("/api/v1/api-keys", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()
        ids = [i["id"] for i in items]
        assert row.id in ids
        item = next(i for i in items if i["id"] == row.id)
        assert item["key_prefix"] == row.key_prefix
        assert "ingest" in item["scopes"]

    def test_list_scoped_to_org(self, client: TestClient, owner_headers: dict, db: Session, org: Organization, org_b: Organization):
        """Keys belonging to org_b must not appear in org's list."""
        _make_api_key(db, org_b.id)
        resp = client.get("/api/v1/api-keys", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()
        # All items must belong to org
        for item in items:
            assert item.get("organization_id", org.id) == org.id


class TestApiKeyRevoke:
    def test_revoke_sets_revoked_at(self, client: TestClient, owner_headers: dict, db: Session, org: Organization):
        _, row = _make_api_key(db, org.id)
        resp = client.post(f"/api/v1/api-keys/{row.id}/revoke", headers=owner_headers)
        assert resp.status_code == 200, resp.text
        db.refresh(row)
        assert row.revoked_at is not None

    def test_revoke_other_org_key_404(self, client: TestClient, owner_headers: dict, db: Session, org: Organization, org_b: Organization):
        _, row_b = _make_api_key(db, org_b.id)
        resp = client.post(f"/api/v1/api-keys/{row_b.id}/revoke", headers=owner_headers)
        assert resp.status_code == 404, resp.text

    def test_member_cannot_revoke(self, client: TestClient, member_headers: dict, db: Session, org: Organization):
        _, row = _make_api_key(db, org.id)
        resp = client.post(f"/api/v1/api-keys/{row.id}/revoke", headers=member_headers)
        assert resp.status_code == 403, resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# § verify_api_key dependency
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerifyApiKey:
    def test_valid_key_is_accepted(self, client: TestClient, db: Session, org: Organization):
        """A well-formed, non-revoked key returns 200 on a read endpoint."""
        raw, _ = _make_api_key(db, org.id, scopes="read")
        _feedback_in_org(db, org.id)
        resp = client.get(
            "/api/public/v1/feedback",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text

    def test_revoked_key_is_rejected(self, client: TestClient, db: Session, org: Organization):
        raw, _ = _make_api_key(db, org.id, scopes="read", revoked=True)
        resp = client.get(
            "/api/public/v1/feedback",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 401, resp.text

    def test_unknown_key_is_rejected(self, client: TestClient, db: Session, org: Organization):
        fake = "rrf_" + secrets.token_urlsafe(24)
        resp = client.get(
            "/api/public/v1/feedback",
            headers={"Authorization": f"Bearer {fake}"},
        )
        assert resp.status_code == 401, resp.text

    def test_x_api_key_header_accepted(self, client: TestClient, db: Session, org: Organization):
        """X-API-Key header is also accepted as an alternative."""
        raw, _ = _make_api_key(db, org.id, scopes="read")
        _feedback_in_org(db, org.id)
        resp = client.get(
            "/api/public/v1/feedback",
            headers={"X-API-Key": raw},
        )
        assert resp.status_code == 200, resp.text

    def test_valid_key_updates_last_used_at(self, client: TestClient, db: Session, org: Organization):
        raw, row = _make_api_key(db, org.id, scopes="read")
        assert row.last_used_at is None
        _feedback_in_org(db, org.id)
        client.get(
            "/api/public/v1/feedback",
            headers={"Authorization": f"Bearer {raw}"},
        )
        db.refresh(row)
        assert row.last_used_at is not None


# ═══════════════════════════════════════════════════════════════════════════════
# § Scope enforcement
# ═══════════════════════════════════════════════════════════════════════════════

class TestScopeEnforcement:
    def test_read_key_can_list_feedback(self, client: TestClient, db: Session, org: Organization):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        _feedback_in_org(db, org.id)
        resp = client.get(
            "/api/public/v1/feedback",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text

    def test_read_only_key_cannot_ingest(self, client: TestClient, db: Session, org: Organization):
        """A key with only `read` scope must be rejected (403) on POST /feedback."""
        raw, _ = _make_api_key(db, org.id, scopes="read")
        resp = client.post(
            "/api/public/v1/feedback",
            json={"text": "test feedback"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_ingest_key_can_post_feedback(self, client: TestClient, db: Session, org: Organization):
        """A key with `ingest` scope succeeds on POST /feedback."""
        raw, _ = _make_api_key(db, org.id, scopes="read,ingest")
        resp = client.post(
            "/api/public/v1/feedback",
            json={"text": "Great product from the API"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "id" in data

    def test_ingest_stores_feedback_in_org(self, client: TestClient, db: Session, org: Organization):
        raw, _ = _make_api_key(db, org.id, scopes="read,ingest")
        resp = client.post(
            "/api/public/v1/feedback",
            json={"text": "Stored in right org"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201, resp.text
        fid = resp.json()["id"]
        row = db.query(FeedbackItem).filter(FeedbackItem.id == fid).first()
        assert row is not None
        assert row.organization_id == org.id


# ═══════════════════════════════════════════════════════════════════════════════
# § Cross-tenant isolation — every read endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossTenantIsolation:
    """A key for org A must never see org B's data."""

    def test_feedback_list_scoped_to_org(
        self, client: TestClient, db: Session, org: Organization, org_b: Organization
    ):
        raw_a, _ = _make_api_key(db, org.id, scopes="read")
        fb_a = _feedback_in_org(db, org.id, "Org A feedback")
        fb_b = _feedback_in_org(db, org_b.id, "Org B feedback")

        resp = client.get(
            "/api/public/v1/feedback",
            headers={"Authorization": f"Bearer {raw_a}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [i["id"] for i in resp.json()["items"]]
        assert fb_a.id in ids
        assert fb_b.id not in ids, "Org B feedback must not be visible to Org A key"

    def test_feedback_detail_cross_tenant_404(
        self, client: TestClient, db: Session, org: Organization, org_b: Organization
    ):
        raw_a, _ = _make_api_key(db, org.id, scopes="read")
        fb_b = _feedback_in_org(db, org_b.id, "Org B only")
        resp = client.get(
            f"/api/public/v1/feedback/{fb_b.id}",
            headers={"Authorization": f"Bearer {raw_a}"},
        )
        assert resp.status_code == 404, resp.text

    def test_analytics_summary_scoped(
        self, client: TestClient, db: Session, org: Organization, org_b: Organization
    ):
        raw_a, _ = _make_api_key(db, org.id, scopes="read")
        _feedback_in_org(db, org.id, "Org A only")
        _feedback_in_org(db, org_b.id, "Org B only")

        resp = client.get(
            "/api/public/v1/analytics/summary",
            headers={"Authorization": f"Bearer {raw_a}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # total_feedback must only count org A's items
        assert data["total_feedback"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# § Public read endpoints — basic smoke tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicReadEndpoints:
    def test_get_feedback_list(self, client: TestClient, db: Session, org: Organization):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        _feedback_in_org(db, org.id)
        resp = client.get(
            "/api/public/v1/feedback",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "items" in body
        assert "total" in body

    def test_get_feedback_by_id(self, client: TestClient, db: Session, org: Organization):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        fb = _feedback_in_org(db, org.id, "hello world")
        resp = client.get(
            f"/api/public/v1/feedback/{fb.id}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == fb.id

    def test_analytics_summary(self, client: TestClient, db: Session, org: Organization):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        _feedback_in_org(db, org.id)
        resp = client.get(
            "/api/public/v1/analytics/summary",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "total_feedback" in data

    def test_no_auth_returns_401(self, client: TestClient, db: Session, org: Organization):
        resp = client.get("/api/public/v1/feedback")
        assert resp.status_code == 401, resp.text


# ═══════════════════════════════════════════════════════════════════════════════
# § Ingest enqueues analysis
# ═══════════════════════════════════════════════════════════════════════════════

class TestIngestEnqueuesAnalysis:
    def test_ingest_calls_queue(self, client: TestClient, db: Session, org: Organization, monkeypatch):
        """POST /feedback must call queue_analyze_feedback with the new item's ID."""
        queued_ids = []

        def fake_queue(feedback_id: int):
            queued_ids.append(feedback_id)

        monkeypatch.setattr(
            "src.api.routes.public_api.queue_analyze_feedback",
            fake_queue,
        )

        raw, _ = _make_api_key(db, org.id, scopes="read,ingest")
        resp = client.post(
            "/api/public/v1/feedback",
            json={"text": "please queue me"},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 201, resp.text
        fid = resp.json()["id"]
        assert fid in queued_ids, "queue_analyze_feedback must be called with the new feedback id"
