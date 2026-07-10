"""
Phase 2 RED: Tests for GET /api/v1/settings/ai/classifier/accuracy
(settings-api-and-accuracy-card aspect, M5.2).

Uses the self-contained test-helper pattern (mirrors test_ai_readiness.py)
rather than the shared test_organization/auth_headers fixtures, because the
cross-org isolation test needs two independent orgs.

Covers:
- Empty org -> 200, has_model=false, label_count=0, is_ready=false,
  min_labels=20, history=[], model_kind label present.
- Seeded active model (label_count=140, macro_f1=0.71) + 3 eval runs ->
  active summary correct, is_ready=true, history ordered newest-first.
- Not-ready: active model with label_count=12 -> is_ready=false, 12 surfaced.
- Cross-org isolation: org B's model/runs never appear for org A's caller.
- Requires auth (no token -> 401).
"""

import os
import sys
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.api.routes.classifier_accuracy import MIN_CLASSIFIER_LABELS
from src.models.org_classifier import OrgClassifierEvalRun, OrgClassifierModel
from src.models.organization import Organization
from src.models.user import User

URL = "/api/v1/settings/ai/classifier/accuracy"


# ---------------------------------------------------------------------------
# Helpers
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
    is_active: bool = True,
    fit_at=None,
) -> OrgClassifierModel:
    model = OrgClassifierModel(
        organization_id=org.id,
        classifier_type="sentiment",
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


def _make_eval_run(
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
        classifier_type="sentiment",
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


class TestClassifierAccuracyEmptyOrg:
    def test_empty_org_returns_no_model_state(self, client: TestClient, db: Session):
        org = _make_org(db, "Empty Org")
        user = _make_user(db, org)

        response = client.get(URL, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is False
        assert body["label_count"] == 0
        assert body["is_ready"] is False
        assert body["min_labels"] == 20
        assert body["history"] == []
        assert body["model_kind"] == "per-org TF-IDF + logistic regression"
        assert body["macro_f1"] is None
        assert body["fit_at"] is None


class TestClassifierAccuracySeeded:
    def test_seeded_model_and_runs_return_correct_summary(self, client: TestClient, db: Session):
        org = _make_org(db, "Seeded Org")
        user = _make_user(db, org)
        model = _make_model(db, org, label_count=140, macro_f1=0.71)

        run1 = _make_eval_run(
            db, org, model, 0.65, 0.71, 0.06, "promoted", 40,
            created_at=datetime.utcnow() - timedelta(days=2),
        )
        run2 = _make_eval_run(
            db, org, model, 0.60, 0.65, 0.05, "promoted", 35,
            created_at=datetime.utcnow() - timedelta(days=9),
        )
        run3 = _make_eval_run(
            db, org, model, 0.58, 0.55, -0.03, "retained", 20,
            created_at=datetime.utcnow() - timedelta(days=16),
        )

        response = client.get(URL, headers=_headers(user))

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
        assert history[0]["decision"] == "promoted"
        assert history[0]["n"] == 40
        assert history[0]["incumbent_macro_f1"] == pytest.approx(0.65)
        assert history[0]["challenger_macro_f1"] == pytest.approx(0.71)
        assert history[0]["macro_f1_delta"] == pytest.approx(0.06)
        assert history[1]["n"] == 35
        assert history[2]["decision"] == "retained"
        assert history[2]["n"] == 20


class TestClassifierAccuracyNotReady:
    def test_not_ready_model_surfaces_count_below_threshold(self, client: TestClient, db: Session):
        org = _make_org(db, "Not Ready Org")
        user = _make_user(db, org)
        _make_model(db, org, label_count=12, macro_f1=None)

        response = client.get(URL, headers=_headers(user))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is True
        assert body["label_count"] == 12
        assert body["is_ready"] is False
        assert body["min_labels"] == 20


class TestClassifierAccuracyCrossOrgIsolation:
    def test_org_a_never_sees_org_b_model_or_runs(self, client: TestClient, db: Session):
        org_a = _make_org(db, "Org A")
        org_b = _make_org(db, "Org B")
        user_a = _make_user(db, org_a)

        model_b = _make_model(db, org_b, label_count=200, macro_f1=0.9)
        _make_eval_run(db, org_b, model_b, 0.8, 0.9, 0.1, "promoted", 50)

        response = client.get(URL, headers=_headers(user_a))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["has_model"] is False
        assert body["label_count"] == 0
        assert body["history"] == []


class TestClassifierAccuracyAuth:
    def test_requires_auth(self, client: TestClient):
        response = client.get(URL)
        # HTTPBearer with no token -> 403 (codebase convention, see
        # test_ai_readiness.py / test_churn_accuracy_api.py's no-auth tests).
        assert response.status_code == 403


class TestMinLabelsParity:
    """Single source of truth: the route's MIN_CLASSIFIER_LABELS must equal
    the core's MIN_LABELS. See classifier_accuracy.py's module docstring for
    why the route does NOT import the analysis-engine package directly.
    """

    def test_min_classifier_labels_equals_core_min_labels(self):
        # See test_classifier_predict_contract.py for why this sys.path
        # insertion is needed locally (Docker-only layout otherwise puts
        # analysis-engine's "analyzer" package on sys.path only inside the
        # production image).
        analysis_engine_src = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../analysis-engine/src")
        )
        if analysis_engine_src not in sys.path:
            sys.path.insert(0, analysis_engine_src)

        from analyzer.corrections_classifier.labels import MIN_LABELS

        assert MIN_CLASSIFIER_LABELS == MIN_LABELS
