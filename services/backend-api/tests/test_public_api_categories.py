"""
Tests for the public custom-categories CRUD — /api/public/v1/categories.

Mirrors the internal /api/v1/categories/custom CRUD (see tests/test_categories.py
and src/services/custom_category_service.py), gated by API-key scopes instead
of JWT roles: GET needs `read`; POST/PATCH/DELETE need `write`.

Self-contained in-memory SQLite engine, mirroring tests/test_public_api_write.py.
"""

import hashlib
import secrets
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.main import app
from src.database.session import get_db
from src.models.api_key import ApiKey
from src.models.automation_rule import AutomationRule
from src.models.custom_category import CustomCategory
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


def _category_in_org(
    db: Session,
    org_id: int,
    name: str = "onboarding_issues",
    category_type: str = "pain_point",
    description: str = None,
) -> CustomCategory:
    cat = CustomCategory(
        organization_id=org_id,
        name=name,
        category_type=category_type,
        description=description,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _auth(raw_key: str) -> dict:
    return {"Authorization": f"Bearer {raw_key}"}


# ═══════════════════════════════════════════════════════════════════════════════
# § GET /categories
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicListCategories:
    def test_requires_read_scope(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="ingest")
        response = client.get("/api/public/v1/categories", headers=_auth(raw))
        assert response.status_code == 403

    def test_bad_key_401(self, client):
        response = client.get(
            "/api/public/v1/categories", headers=_auth("rrf_not-a-real-key")
        )
        assert response.status_code == 401

    def test_lists_org_scoped(self, client, db, org, org_b):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        _category_in_org(db, org.id, name="cat_a")
        _category_in_org(db, org_b.id, name="cat_from_other_org")

        response = client.get("/api/public/v1/categories", headers=_auth(raw))
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "cat_a"

    def test_filters_by_category_type(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        _category_in_org(db, org.id, name="pain_a", category_type="pain_point")
        _category_in_org(db, org.id, name="feat_a", category_type="feature_request")

        response = client.get(
            "/api/public/v1/categories?category_type=pain_point", headers=_auth(raw)
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["category_type"] == "pain_point"

    def test_empty_list(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        response = client.get("/api/public/v1/categories", headers=_auth(raw))
        assert response.status_code == 200
        assert response.json() == []


# ═══════════════════════════════════════════════════════════════════════════════
# § POST /categories
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicCreateCategory:
    def test_requires_write_scope(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        response = client.post(
            "/api/public/v1/categories",
            headers=_auth(raw),
            json={"name": "new_cat", "category_type": "pain_point"},
        )
        assert response.status_code == 403

    def test_create_success(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.post(
            "/api/public/v1/categories",
            headers=_auth(raw),
            json={
                "name": "api_requests",
                "description": "API-related feature requests",
                "category_type": "feature_request",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "api_requests"
        assert data["category_type"] == "feature_request"
        assert data["is_active"] is True
        assert data["description"] == "API-related feature requests"

    def test_rejects_duplicate_org_type_name(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        _category_in_org(db, org.id, name="onboarding_issues", category_type="pain_point")

        response = client.post(
            "/api/public/v1/categories",
            headers=_auth(raw),
            json={"name": "onboarding_issues", "category_type": "pain_point"},
        )
        assert response.status_code == 409

    def test_allows_same_name_different_type(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        _category_in_org(db, org.id, name="onboarding_issues", category_type="pain_point")

        response = client.post(
            "/api/public/v1/categories",
            headers=_auth(raw),
            json={"name": "onboarding_issues", "category_type": "feature_request"},
        )
        assert response.status_code == 201

    def test_invalid_category_type_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.post(
            "/api/public/v1/categories",
            headers=_auth(raw),
            json={"name": "test", "category_type": "invalid_type"},
        )
        assert response.status_code == 422

    def test_unknown_field_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.post(
            "/api/public/v1/categories",
            headers=_auth(raw),
            json={
                "name": "test",
                "category_type": "pain_point",
                "not_a_real_field": "oops",
            },
        )
        assert response.status_code == 422

    def test_name_too_long_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.post(
            "/api/public/v1/categories",
            headers=_auth(raw),
            json={"name": "x" * 101, "category_type": "pain_point"},
        )
        assert response.status_code == 422

    def test_empty_name_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.post(
            "/api/public/v1/categories",
            headers=_auth(raw),
            json={"name": "", "category_type": "pain_point"},
        )
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# § PATCH /categories/{id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicUpdateCategory:
    def test_requires_write_scope(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        cat = _category_in_org(db, org.id)
        response = client.patch(
            f"/api/public/v1/categories/{cat.id}",
            headers=_auth(raw),
            json={"name": "renamed"},
        )
        assert response.status_code == 403

    def test_update_name(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        cat = _category_in_org(db, org.id)
        response = client.patch(
            f"/api/public/v1/categories/{cat.id}",
            headers=_auth(raw),
            json={"name": "updated_name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated_name"

    def test_toggle_active(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        cat = _category_in_org(db, org.id)
        response = client.patch(
            f"/api/public/v1/categories/{cat.id}",
            headers=_auth(raw),
            json={"is_active": False},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_not_found(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.patch(
            "/api/public/v1/categories/9999",
            headers=_auth(raw),
            json={"name": "new_name"},
        )
        assert response.status_code == 404

    def test_other_org_404(self, client, db, org, org_b):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        other_cat = _category_in_org(db, org_b.id, name="other_org_cat")
        response = client.patch(
            f"/api/public/v1/categories/{other_cat.id}",
            headers=_auth(raw),
            json={"name": "hacked"},
        )
        assert response.status_code == 404

    def test_rename_collision_409(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        _category_in_org(db, org.id, name="billing_issues")
        other = _category_in_org(db, org.id, name="shipping_issues")

        response = client.patch(
            f"/api/public/v1/categories/{other.id}",
            headers=_auth(raw),
            json={"name": "billing_issues"},
        )
        assert response.status_code == 409

    def test_category_type_not_editable_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        cat = _category_in_org(db, org.id)
        response = client.patch(
            f"/api/public/v1/categories/{cat.id}",
            headers=_auth(raw),
            json={"category_type": "feature_request"},
        )
        assert response.status_code == 422

    def test_unknown_field_422(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        cat = _category_in_org(db, org.id)
        response = client.patch(
            f"/api/public/v1/categories/{cat.id}",
            headers=_auth(raw),
            json={"not_a_real_field": "oops"},
        )
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# § DELETE /categories/{id}
# ═══════════════════════════════════════════════════════════════════════════════

class TestPublicDeleteCategory:
    def test_requires_write_scope(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="read")
        cat = _category_in_org(db, org.id)
        response = client.delete(
            f"/api/public/v1/categories/{cat.id}", headers=_auth(raw)
        )
        assert response.status_code == 403

    def test_delete_success_no_warning_header(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        cat = _category_in_org(db, org.id, name="onboarding_issues")

        response = client.delete(
            f"/api/public/v1/categories/{cat.id}", headers=_auth(raw)
        )
        assert response.status_code == 204
        assert "X-Rereflect-Warning" not in response.headers

        remaining = (
            db.query(CustomCategory).filter(CustomCategory.id == cat.id).first()
        )
        assert remaining is None

    def test_not_found(self, client, db, org):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.delete(
            "/api/public/v1/categories/9999", headers=_auth(raw)
        )
        assert response.status_code == 404

    def test_other_org_404(self, client, db, org, org_b):
        raw, _ = _make_api_key(db, org.id, scopes="write")
        other_cat = _category_in_org(db, org_b.id, name="other_org_cat")
        response = client.delete(
            f"/api/public/v1/categories/{other_cat.id}", headers=_auth(raw)
        )
        assert response.status_code == 404
        # Not actually deleted (belongs to org_b, not the caller's org)
        still_there = (
            db.query(CustomCategory).filter(CustomCategory.id == other_cat.id).first()
        )
        assert still_there is not None

    def test_delete_with_active_rule_reference_sets_warning_header(
        self, client, db, org
    ):
        cat = _category_in_org(db, org.id, name="Billing")
        rule = AutomationRule(
            organization_id=org.id,
            name="Billing escalation",
            trigger_type="feedback_category_match",
            trigger_config={"categories": ["Billing"]},
            actions=[{"type": "send_notification", "config": {"channel": "email"}}],
            is_active=True,
        )
        db.add(rule)
        db.commit()

        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.delete(
            f"/api/public/v1/categories/{cat.id}", headers=_auth(raw)
        )
        assert response.status_code == 204
        assert "X-Rereflect-Warning" in response.headers
        warning = response.headers["X-Rereflect-Warning"]
        assert "Billing" in warning
        assert "Billing escalation" in warning

    def test_delete_with_inactive_rule_reference_no_warning_header(
        self, client, db, org
    ):
        cat = _category_in_org(db, org.id, name="Billing")
        rule = AutomationRule(
            organization_id=org.id,
            name="Inactive billing rule",
            trigger_type="feedback_category_match",
            trigger_config={"categories": ["Billing"]},
            actions=[{"type": "send_notification", "config": {"channel": "email"}}],
            is_active=False,
        )
        db.add(rule)
        db.commit()

        raw, _ = _make_api_key(db, org.id, scopes="write")
        response = client.delete(
            f"/api/public/v1/categories/{cat.id}", headers=_auth(raw)
        )
        assert response.status_code == 204
        assert "X-Rereflect-Warning" not in response.headers
