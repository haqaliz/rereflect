"""
Phase 3 RED->GREEN: Tests for classifier-model-versioning-rollback aspect
(backend-routes): classifier_type validation (M8), GET .../classifier/versions
(M6), durable rollback with to_version_id + hold engagement (M3/M4), audit
(M7), and POST .../classifier/resume (M5).

Mirrors test_classifier_accuracy_route.py's / test_classifier_rollback.py's
self-contained test-helper pattern.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.audit_log import AuditLog
from src.models.org_ai_config import OrgAIConfig
from src.models.org_classifier import OrgClassifierModel
from src.models.organization import Organization
from src.models.user import User

VERSIONS_URL = "/api/v1/settings/ai/classifier/versions"
ROLLBACK_URL = "/api/v1/settings/ai/classifier/rollback"
RESUME_URL = "/api/v1/settings/ai/classifier/resume"


# ---------------------------------------------------------------------------
# Helpers (mirrors test_classifier_rollback.py)
# ---------------------------------------------------------------------------


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
    classifier_type: str = "sentiment",
) -> OrgClassifierModel:
    model = OrgClassifierModel(
        organization_id=org.id,
        classifier_type=classifier_type,
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


# ---------------------------------------------------------------------------
# M8: classifier_type validation
# ---------------------------------------------------------------------------


class TestClassifierTypeValidation:
    def test_versions_rejects_unknown_classifier_type(self, client: TestClient, db: Session):
        org = _make_org(db, "Bad Type Org Versions")
        user = _make_user(db, org)

        response = client.get(VERSIONS_URL, params={"classifier_type": "bogus"}, headers=_headers(user))

        assert response.status_code == 400

    def test_rollback_rejects_unknown_classifier_type(self, client: TestClient, db: Session):
        org = _make_org(db, "Bad Type Org Rollback")
        user = _make_user(db, org, role="admin")

        response = client.post(ROLLBACK_URL, params={"classifier_type": "bogus"}, headers=_headers(user))

        assert response.status_code == 400

    def test_resume_rejects_unknown_classifier_type(self, client: TestClient, db: Session):
        org = _make_org(db, "Bad Type Org Resume")
        user = _make_user(db, org, role="admin")

        response = client.post(RESUME_URL, params={"classifier_type": "bogus"}, headers=_headers(user))

        assert response.status_code == 400


# ---------------------------------------------------------------------------
# M6: GET /classifier/versions
# ---------------------------------------------------------------------------


class TestClassifierVersionsList:
    def test_returns_all_versions_newest_first(self, client: TestClient, db: Session):
        org = _make_org(db, "Versions Org")
        user = _make_user(db, org)

        v1 = _make_model(
            db, org, label_count=50, macro_f1=0.50, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=20),
        )
        v2 = _make_model(
            db, org, label_count=100, macro_f1=0.60, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=10),
        )
        v3 = _make_model(
            db, org, label_count=140, macro_f1=0.71, is_active=True,
            fit_at=datetime.utcnow(),
        )

        response = client.get(VERSIONS_URL, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["classifier_type"] == "sentiment"
        assert body["hold"] is False
        versions = body["versions"]
        assert len(versions) == 3
        assert [v["id"] for v in versions] == [v3.id, v2.id, v1.id]
        assert versions[0]["is_active"] is True
        assert versions[1]["is_active"] is False
        assert versions[2]["is_active"] is False
        assert versions[0]["macro_f1"] == pytest.approx(0.71)
        assert versions[0]["label_count"] == 140

    def test_hold_reflects_config(self, client: TestClient, db: Session):
        org = _make_org(db, "Versions Hold Org")
        user = _make_user(db, org)
        _make_model(
            db, org, label_count=50, macro_f1=0.5, is_active=True, fit_at=datetime.utcnow()
        )
        config = OrgAIConfig(
            organization_id=org.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_autopromote_hold=True,
        )
        db.add(config)
        db.commit()

        response = client.get(VERSIONS_URL, headers=_headers(user))

        assert response.status_code == 200, response.text
        assert response.json()["hold"] is True

    def test_cross_org_versions_invisible(self, client: TestClient, db: Session):
        org_a = _make_org(db, "Versions Org A")
        org_b = _make_org(db, "Versions Org B")
        user_a = _make_user(db, org_a)

        _make_model(
            db, org_b, label_count=200, macro_f1=0.9, is_active=True, fit_at=datetime.utcnow()
        )

        response = client.get(VERSIONS_URL, headers=_headers(user_a))

        assert response.status_code == 200, response.text
        assert response.json()["versions"] == []

    def test_member_role_allowed_read(self, client: TestClient, db: Session):
        org = _make_org(db, "Versions Member Org")
        member = _make_user(db, org, role="member")
        _make_model(
            db, org, label_count=50, macro_f1=0.5, is_active=True, fit_at=datetime.utcnow()
        )

        response = client.get(VERSIONS_URL, headers=_headers(member))

        assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# M3/M4: rollback with to_version_id + hold engagement + audit (M7)
# ---------------------------------------------------------------------------


class TestRollbackToSpecificVersion:
    def test_rollback_to_version_id_activates_exactly_that_version(
        self, client: TestClient, db: Session
    ):
        org = _make_org(db, "Targeted Rollback Org")
        user = _make_user(db, org, role="admin")

        v1 = _make_model(
            db, org, label_count=50, macro_f1=0.50, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=20),
        )
        v2 = _make_model(
            db, org, label_count=100, macro_f1=0.60, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=10),
        )
        v3 = _make_model(
            db, org, label_count=140, macro_f1=0.71, is_active=True,
            fit_at=datetime.utcnow(),
        )

        response = client.post(
            ROLLBACK_URL,
            params={"classifier_type": "sentiment", "to_version_id": v1.id},
            headers=_headers(user),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is True
        assert body["label_count"] == 50
        assert body["hold"] is True

        db.refresh(v1)
        db.refresh(v2)
        db.refresh(v3)
        assert v1.is_active is True
        assert v2.is_active is False
        assert v3.is_active is False

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

        audit_row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "classifier_rolled_back", AuditLog.organization_id == org.id)
            .first()
        )
        assert audit_row is not None
        assert audit_row.details["from_model_id"] == v3.id
        assert audit_row.details["to_model_id"] == v1.id
        assert audit_row.details["held"] is True
        assert audit_row.target_id == v1.id
        assert audit_row.user_email == user.email

    def test_rollback_to_version_id_cross_org_returns_404(self, client: TestClient, db: Session):
        org_a = _make_org(db, "Targeted Org A")
        org_b = _make_org(db, "Targeted Org B")
        user_a = _make_user(db, org_a, role="admin")

        _make_model(
            db, org_a, label_count=50, macro_f1=0.5, is_active=True, fit_at=datetime.utcnow()
        )
        other_org_version = _make_model(
            db, org_b, label_count=90, macro_f1=0.65, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=5),
        )

        response = client.post(
            ROLLBACK_URL,
            params={"classifier_type": "sentiment", "to_version_id": other_org_version.id},
            headers=_headers(user_a),
        )

        assert response.status_code == 404

    def test_rollback_to_version_id_wrong_type_returns_404(self, client: TestClient, db: Session):
        org = _make_org(db, "Targeted Wrong Type Org")
        user = _make_user(db, org, role="admin")

        _make_model(
            db, org, label_count=50, macro_f1=0.5, is_active=True, fit_at=datetime.utcnow(),
            classifier_type="sentiment",
        )
        category_version = _make_model(
            db, org, label_count=80, macro_f1=0.6, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=5), classifier_type="category",
        )

        response = client.post(
            ROLLBACK_URL,
            params={"classifier_type": "sentiment", "to_version_id": category_version.id},
            headers=_headers(user),
        )

        assert response.status_code == 404


class TestDisableOnlyRollbackHoldBehavior:
    def test_disable_only_rollback_does_not_engage_hold(self, client: TestClient, db: Session):
        org = _make_org(db, "Disable Only Hold Org")
        user = _make_user(db, org, role="admin")

        only_model = _make_model(
            db, org, label_count=50, macro_f1=0.55, is_active=True, fit_at=datetime.utcnow()
        )

        response = client.post(ROLLBACK_URL, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is False
        assert body["hold"] is False

        audit_row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "classifier_rolled_back", AuditLog.organization_id == org.id)
            .first()
        )
        assert audit_row is not None
        assert audit_row.details["held"] is False
        assert audit_row.details["to_model_id"] is None

        # Idempotent-safe re-call still 404s.
        second_response = client.post(ROLLBACK_URL, headers=_headers(user))
        assert second_response.status_code == 404


# ---------------------------------------------------------------------------
# M5: resume
# ---------------------------------------------------------------------------


class TestResumeClassifier:
    def test_resume_clears_hold(self, client: TestClient, db: Session):
        org = _make_org(db, "Resume Org")
        user = _make_user(db, org, role="admin")
        config = OrgAIConfig(
            organization_id=org.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_autopromote_hold=True,
        )
        db.add(config)
        db.commit()

        response = client.post(RESUME_URL, headers=_headers(user))

        assert response.status_code == 200, response.text
        assert response.json()["hold"] is False

        db.refresh(config)
        assert config.sentiment_autopromote_hold is False

        audit_row = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "classifier_autopromote_resumed",
                AuditLog.organization_id == org.id,
            )
            .first()
        )
        assert audit_row is not None
        assert audit_row.details["classifier_type"] == "sentiment"

    def test_resume_idempotent_second_call_200(self, client: TestClient, db: Session):
        org = _make_org(db, "Resume Idempotent Org")
        user = _make_user(db, org, role="admin")

        first = client.post(RESUME_URL, headers=_headers(user))
        second = client.post(RESUME_URL, headers=_headers(user))

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["hold"] is False
        assert second.json()["hold"] is False

    def test_resume_member_forbidden(self, client: TestClient, db: Session):
        org = _make_org(db, "Resume Member Org")
        member = _make_user(db, org, role="member")

        response = client.post(RESUME_URL, headers=_headers(member))

        assert response.status_code == 403
