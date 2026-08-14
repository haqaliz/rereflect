"""
Phase 2 RED: Tests for classifier_type='churn' across accuracy/versions/rollback/
resume (services/backend-api/src/api/routes/classifier_accuracy.py).

Purely additive: extends VALID_CLASSIFIER_TYPES + _HOLD_COLUMN_BY_TYPE with
"churn"; the endpoints are already generic via classifier_type. Mirrors
test_classifier_accuracy_route.py / test_classifier_versions.py /
test_classifier_rollback.py's self-contained test-helper pattern.

Covers:
- GET .../classifier/accuracy?classifier_type=churn: empty state (no model)
  and incumbent-vs-challenger card with a seeded org churn model + eval runs
  (decisions incl. 'held' / 'promoted_candidate' — the churn trainer's
  consecutive-runs decisions), newest-first.
- GET .../classifier/versions?classifier_type=churn: newest-first + hold flag.
- POST .../classifier/rollback?classifier_type=churn: reactivate-prior engages
  churn_autopromote_hold, disable-only does not, 404 when nothing active,
  404 cross-org to_version_id, member -> 403.
- POST .../classifier/resume?classifier_type=churn: clears
  churn_autopromote_hold, idempotent, member -> 403.

TDD: RED first, then production code (VALID_CLASSIFIER_TYPES + _HOLD_COLUMN_BY_TYPE).
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.org_ai_config import OrgAIConfig
from src.models.org_classifier import OrgClassifierEvalRun, OrgClassifierModel
from src.models.organization import Organization
from src.models.user import User

ACCURACY_URL = "/api/v1/settings/ai/classifier/accuracy"
VERSIONS_URL = "/api/v1/settings/ai/classifier/versions"
ROLLBACK_URL = "/api/v1/settings/ai/classifier/rollback"
RESUME_URL = "/api/v1/settings/ai/classifier/resume"

CHURN = "churn"


# ---------------------------------------------------------------------------
# Helpers (mirrors test_classifier_versions.py)
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


def _make_churn_model(
    db: Session,
    org: Organization,
    label_count: int,
    macro_f1,
    is_active: bool,
    fit_at=None,
) -> OrgClassifierModel:
    model = OrgClassifierModel(
        organization_id=org.id,
        classifier_type=CHURN,
        model_json={"vectorizer": {}, "logreg": {}, "classes": []},
        label_count=label_count,
        macro_f1=macro_f1,
        fit_at=fit_at or datetime.utcnow(),
        is_active=is_active,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _make_churn_eval_run(
    db: Session,
    org: Organization,
    model: OrgClassifierModel,
    incumbent_macro_f1,
    challenger_macro_f1,
    macro_f1_delta,
    decision: str,
    n: int,
    created_at=None,
) -> OrgClassifierEvalRun:
    run = OrgClassifierEvalRun(
        organization_id=org.id,
        classifier_model_id=model.id,
        classifier_type=CHURN,
        incumbent_macro_f1=incumbent_macro_f1,
        challenger_macro_f1=challenger_macro_f1,
        macro_f1_delta=macro_f1_delta,
        decision=decision,
        n=n,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _make_hold_config(db: Session, org: Organization, held: bool = True) -> OrgAIConfig:
    config = OrgAIConfig(
        organization_id=org.id,
        default_provider="openai",
        model_categorization="gpt-4o-mini",
        model_analysis="gpt-4o-mini",
        model_insights="gpt-4o-mini",
        churn_autopromote_hold=held,
    )
    db.add(config)
    db.commit()
    return config


# ---------------------------------------------------------------------------
# GET /classifier/accuracy?classifier_type=churn
# ---------------------------------------------------------------------------


class TestChurnAccuracyEmptyOrg:
    def test_empty_org_returns_no_model_state(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Empty Org")
        user = _make_user(db, org)

        response = client.get(ACCURACY_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["classifier_type"] == CHURN
        assert body["has_model"] is False
        assert body["label_count"] == 0
        assert body["is_ready"] is False
        assert body["min_labels"] == 20
        assert body["history"] == []
        assert body["macro_f1"] is None
        assert body["fit_at"] is None
        assert body["hold"] is False


class TestChurnAccuracySeeded:
    def test_seeded_churn_model_and_runs_return_correct_summary(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Seeded Org")
        user = _make_user(db, org)
        model = _make_churn_model(db, org, label_count=140, macro_f1=0.71, is_active=True)

        _make_churn_eval_run(
            db, org, model, 0.65, 0.71, 0.06, "held", 40,
            created_at=datetime.utcnow() - timedelta(days=2),
        )
        _make_churn_eval_run(
            db, org, model, 0.60, 0.65, 0.05, "promoted_candidate", 35,
            created_at=datetime.utcnow() - timedelta(days=9),
        )
        _make_churn_eval_run(
            db, org, model, 0.58, 0.55, -0.03, "skipped", 20,
            created_at=datetime.utcnow() - timedelta(days=16),
        )

        response = client.get(ACCURACY_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is True
        assert body["label_count"] == 140
        assert body["macro_f1"] == pytest.approx(0.71)
        assert body["fit_at"] is not None
        assert body["is_ready"] is True
        assert body["min_labels"] == 20

        history = body["history"]
        assert len(history) == 3
        # newest-first
        assert history[0]["decision"] == "held"
        assert history[0]["n"] == 40
        assert history[0]["incumbent_macro_f1"] == pytest.approx(0.65)
        assert history[0]["challenger_macro_f1"] == pytest.approx(0.71)
        assert history[0]["macro_f1_delta"] == pytest.approx(0.06)
        assert history[1]["decision"] == "promoted_candidate"
        assert history[1]["n"] == 35
        assert history[2]["decision"] == "skipped"
        assert history[2]["n"] == 20

    def test_churn_hold_surfaces(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Hold Org")
        user = _make_user(db, org)
        _make_churn_model(db, org, label_count=50, macro_f1=0.5, is_active=True)
        _make_hold_config(db, org, held=True)

        response = client.get(ACCURACY_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 200, response.text
        assert response.json()["hold"] is True


# ---------------------------------------------------------------------------
# GET /classifier/versions?classifier_type=churn
# ---------------------------------------------------------------------------


class TestChurnVersionsList:
    def test_returns_all_churn_versions_newest_first(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Versions Org")
        user = _make_user(db, org)

        v1 = _make_churn_model(
            db, org, label_count=50, macro_f1=0.50, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=20),
        )
        v2 = _make_churn_model(
            db, org, label_count=100, macro_f1=0.60, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=10),
        )
        v3 = _make_churn_model(
            db, org, label_count=140, macro_f1=0.71, is_active=True,
            fit_at=datetime.utcnow(),
        )

        response = client.get(VERSIONS_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["classifier_type"] == CHURN
        assert body["hold"] is False
        versions = body["versions"]
        assert len(versions) == 3
        assert [v["id"] for v in versions] == [v3.id, v2.id, v1.id]
        assert versions[0]["is_active"] is True
        assert versions[1]["is_active"] is False
        assert versions[2]["is_active"] is False
        assert versions[0]["macro_f1"] == pytest.approx(0.71)
        assert versions[0]["label_count"] == 140

    def test_churn_hold_reflects_config(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Versions Hold Org")
        user = _make_user(db, org)
        _make_churn_model(db, org, label_count=50, macro_f1=0.5, is_active=True)
        _make_hold_config(db, org, held=True)

        response = client.get(VERSIONS_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 200, response.text
        assert response.json()["hold"] is True


# ---------------------------------------------------------------------------
# POST /classifier/rollback?classifier_type=churn
# ---------------------------------------------------------------------------


class TestChurnRollbackReactivatesPrior:
    def test_rollback_flips_prior_active_and_engages_churn_hold(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Rollback Org")
        user = _make_user(db, org, role="admin")

        v1 = _make_churn_model(
            db, org, label_count=100, macro_f1=0.60, is_active=False,
            fit_at=datetime.utcnow() - timedelta(days=10),
        )
        v2 = _make_churn_model(
            db, org, label_count=140, macro_f1=0.71, is_active=True,
            fit_at=datetime.utcnow(),
        )

        response = client.post(ROLLBACK_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is True
        assert body["label_count"] == 100
        assert body["macro_f1"] == pytest.approx(0.60)
        assert body["hold"] is True

        db.refresh(v1)
        db.refresh(v2)
        assert v1.is_active is True
        assert v2.is_active is False

        config = db.query(OrgAIConfig).filter_by(organization_id=org.id).first()
        assert config is not None
        assert config.churn_autopromote_hold is True

        active_count = (
            db.query(OrgClassifierModel)
            .filter(
                OrgClassifierModel.organization_id == org.id,
                OrgClassifierModel.classifier_type == CHURN,
                OrgClassifierModel.is_active.is_(True),
            )
            .count()
        )
        assert active_count == 1


class TestChurnRollbackNoPriorVersion:
    def test_disable_only_rollback_does_not_engage_churn_hold(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Single Version Org")
        user = _make_user(db, org, role="admin")

        only_model = _make_churn_model(
            db, org, label_count=50, macro_f1=0.55, is_active=True, fit_at=datetime.utcnow()
        )

        response = client.post(ROLLBACK_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is False
        assert body["label_count"] == 0
        assert body["hold"] is False

        db.refresh(only_model)
        assert only_model.is_active is False

        # Idempotent-safe: nothing left to roll back -> 404, not a crash.
        second_response = client.post(ROLLBACK_URL, params={"classifier_type": CHURN}, headers=_headers(user))
        assert second_response.status_code == 404


class TestChurnRollbackNoModelAtAll:
    def test_rollback_with_no_model_returns_404(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn No Model Org")
        user = _make_user(db, org, role="admin")

        response = client.post(ROLLBACK_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 404


class TestChurnRollbackCrossOrgIsolation:
    def test_cannot_roll_back_another_orgs_churn_model(self, client: TestClient, db: Session):
        org_a = _make_org(db, "Churn Org A")
        org_b = _make_org(db, "Churn Org B")
        user_a = _make_user(db, org_a, role="admin")

        _make_churn_model(db, org_b, label_count=200, macro_f1=0.9, is_active=True)

        response = client.post(ROLLBACK_URL, params={"classifier_type": CHURN}, headers=_headers(user_a))

        assert response.status_code == 404


class TestChurnRollbackRequiresAdminOrOwner:
    def test_member_forbidden(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Member Org")
        member = _make_user(db, org, role="member")
        _make_churn_model(db, org, label_count=50, macro_f1=0.55, is_active=True)

        response = client.post(ROLLBACK_URL, params={"classifier_type": CHURN}, headers=_headers(member))

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /classifier/resume?classifier_type=churn
# ---------------------------------------------------------------------------


class TestChurnResumeClassifier:
    def test_resume_clears_churn_hold(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Resume Org")
        user = _make_user(db, org, role="admin")
        config = _make_hold_config(db, org, held=True)
        _make_churn_model(db, org, label_count=50, macro_f1=0.55, is_active=True)

        response = client.post(RESUME_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert response.status_code == 200, response.text
        assert response.json()["hold"] is False

        db.refresh(config)
        assert config.churn_autopromote_hold is False

    def test_resume_idempotent_second_call_200(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Resume Idempotent Org")
        user = _make_user(db, org, role="admin")

        first = client.post(RESUME_URL, params={"classifier_type": CHURN}, headers=_headers(user))
        second = client.post(RESUME_URL, params={"classifier_type": CHURN}, headers=_headers(user))

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["hold"] is False
        assert second.json()["hold"] is False

    def test_resume_member_forbidden(self, client: TestClient, db: Session):
        org = _make_org(db, "Churn Resume Member Org")
        member = _make_user(db, org, role="member")

        response = client.post(RESUME_URL, params={"classifier_type": CHURN}, headers=_headers(member))

        assert response.status_code == 403
