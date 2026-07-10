"""
Phase 3 RED: Tests for POST /api/v1/settings/ai/classifier/rollback
(settings-api-and-accuracy-card aspect, M5.2 — optional should-have,
included). Mirrors test_classifier_accuracy_route.py's self-contained
test-helper pattern for cross-org isolation.

Covers:
- Seeded active v2 + inactive prior v1 -> rollback flips v1 active, v2
  inactive; response reflects v1; exactly one active row remains.
- No prior version (only one active model) -> deactivates it, has_model=false
  afterward; idempotent-safe (calling again 404s, nothing left to roll back).
- No model at all -> 404.
- Requires admin/owner (member -> 403).
- Cross-org: cannot roll back another org's model (404, not leaked).
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.org_classifier import OrgClassifierModel
from src.models.organization import Organization
from src.models.user import User

URL = "/api/v1/settings/ai/classifier/rollback"


def _make_org(db: Session, name: str = "") -> Organization:
    org = Organization(name=name or f"Org-{id(db)}-{datetime.utcnow().timestamp()}", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"u{org.id}-{role}-{datetime.utcnow().timestamp()}@example.com",
        password_hash=hash_password("pw"),
        organization_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token(
        {"user_id": user.id, "organization_id": user.organization_id, "role": user.role}
    )
    return {"Authorization": f"Bearer {token}"}


def _make_model(
    db: Session,
    org: Organization,
    label_count: int,
    macro_f1,
    is_active: bool,
    fit_at,
) -> OrgClassifierModel:
    model = OrgClassifierModel(
        organization_id=org.id,
        classifier_type="sentiment",
        model_json={"vectorizer": {}, "logreg": {}, "classes": []},
        label_count=label_count,
        macro_f1=macro_f1,
        fit_at=fit_at,
        is_active=is_active,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


class TestRollbackReactivatesPrior:
    def test_rollback_flips_prior_active_and_current_inactive(self, client: TestClient, db: Session):
        org = _make_org(db, "Rollback Org")
        user = _make_user(db, org, role="admin")

        v1 = _make_model(
            db, org, label_count=100, macro_f1=0.60, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=10),
        )
        v2 = _make_model(
            db, org, label_count=140, macro_f1=0.71, is_active=True,
            fit_at=datetime.utcnow(),
        )

        response = client.post(URL, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is True
        assert body["label_count"] == 100
        assert body["macro_f1"] == pytest.approx(0.60)

        db.refresh(v1)
        db.refresh(v2)
        assert v1.is_active is True
        assert v2.is_active is False

        active_count = (
            db.query(OrgClassifierModel)
            .filter(
                OrgClassifierModel.organization_id == org.id,
                OrgClassifierModel.classifier_type == "sentiment",
                OrgClassifierModel.is_active.is_(True),
            )
            .count()
        )
        assert active_count == 1


class TestRollbackNoPriorVersion:
    def test_rollback_disables_active_model_when_no_prior_exists(self, client: TestClient, db: Session):
        org = _make_org(db, "Single Version Org")
        user = _make_user(db, org, role="admin")

        only_model = _make_model(
            db, org, label_count=50, macro_f1=0.55, is_active=True, fit_at=datetime.utcnow()
        )

        response = client.post(URL, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is False
        assert body["label_count"] == 0

        db.refresh(only_model)
        assert only_model.is_active is False

        # Idempotent-safe: nothing left to roll back -> 404, not a crash.
        second_response = client.post(URL, headers=_headers(user))
        assert second_response.status_code == 404


class TestRollbackNoModelAtAll:
    def test_rollback_with_no_model_returns_404(self, client: TestClient, db: Session):
        org = _make_org(db, "No Model Org")
        user = _make_user(db, org, role="admin")

        response = client.post(URL, headers=_headers(user))

        assert response.status_code == 404


class TestRollbackRequiresAdminOrOwner:
    def test_member_forbidden(self, client: TestClient, db: Session):
        org = _make_org(db, "Member Org")
        member = _make_user(db, org, role="member")
        _make_model(
            db, org, label_count=50, macro_f1=0.55, is_active=True, fit_at=datetime.utcnow()
        )

        response = client.post(URL, headers=_headers(member))

        assert response.status_code == 403


class TestRollbackCrossOrgIsolation:
    def test_cannot_roll_back_another_orgs_model(self, client: TestClient, db: Session):
        org_a = _make_org(db, "Org A Rollback")
        org_b = _make_org(db, "Org B Rollback")
        user_a = _make_user(db, org_a, role="admin")

        _make_model(
            db, org_b, label_count=200, macro_f1=0.9, is_active=True, fit_at=datetime.utcnow()
        )

        response = client.post(URL, headers=_headers(user_a))

        assert response.status_code == 404
