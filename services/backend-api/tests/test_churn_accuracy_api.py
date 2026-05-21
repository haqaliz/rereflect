"""
Tests for churn accuracy API endpoints (M4.1 Phase 6.2a) — strict TDD.

Endpoints under test:
  GET /api/v1/analytics/churn-accuracy          — org-level card (Business+)
  GET /api/v1/system/churn-accuracy             — cross-org admin overview
  GET /api/v1/system/churn-accuracy/{org_id}/history — per-org model history

All tests run on SQLite in-memory (same pattern as test_churn_cohorts_api.py).
"""

from datetime import datetime, timedelta
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.churn_calibration import ChurnBacktestRun, ChurnCalibrationModel
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session, plan: str = "business", name: str = "") -> Organization:
    """Create an organization with the given plan."""
    org = Organization(name=name or f"Org-{plan}-{id(db)}", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(
    db: Session,
    org: Organization,
    role: str = "admin",
    is_system_admin: bool = False,
) -> User:
    """Create a user, optionally a system admin."""
    user = User(
        email=f"u{org.id}-{is_system_admin}-{role}@example.com",
        password_hash=hash_password("pw"),
        organization_id=org.id,
        role=role,
        is_system_admin=is_system_admin,
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


def _make_calibration_model(
    db: Session,
    org_id: Optional[int],
    *,
    is_active: bool = True,
    label_count: int = 50,
    positive_count: int = 10,
    f1: Optional[float] = 0.72,
    precision: Optional[float] = 0.75,
    recall: Optional[float] = 0.69,
    auc: Optional[float] = 0.81,
    fit_at: Optional[datetime] = None,
) -> ChurnCalibrationModel:
    """Create a ChurnCalibrationModel row."""
    model = ChurnCalibrationModel(
        organization_id=org_id,
        model_json={"type": "isotonic", "X": [0, 50, 100], "y": [0.0, 0.5, 1.0]},
        label_count=label_count,
        positive_count=positive_count,
        precision=precision,
        recall=recall,
        f1=f1,
        auc=auc,
        threshold_bands={"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85},
        fit_at=fit_at or datetime.utcnow(),
        is_active=is_active,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _make_backtest_run(
    db: Session,
    org_id: Optional[int],
    model: ChurnCalibrationModel,
    *,
    run_at: Optional[datetime] = None,
    label_count: int = 50,
    f1: Optional[float] = 0.70,
    precision: Optional[float] = 0.73,
    recall: Optional[float] = 0.67,
    auc: Optional[float] = 0.79,
) -> ChurnBacktestRun:
    """Create a ChurnBacktestRun row."""
    run = ChurnBacktestRun(
        organization_id=org_id,
        calibration_model_id=model.id,
        run_at=run_at or datetime.utcnow(),
        label_count=label_count,
        precision=precision,
        recall=recall,
        f1=f1,
        auc=auc,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


ORG_CARD_URL = "/api/v1/analytics/churn-accuracy"
SYS_URL = "/api/v1/system/churn-accuracy"


# ===========================================================================
# Org accuracy card
# ===========================================================================


def test_get_accuracy_card_blocked_for_pro_plan_returns_403(
    client: TestClient, db: Session
):
    """Pro plan does not include churn_accuracy_card — expect 403."""
    org = _make_org(db, plan="pro")
    user = _make_user(db, org)
    resp = client.get(ORG_CARD_URL, headers=_headers(user))
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["feature"] == "churn_accuracy_card"


def test_get_accuracy_card_returns_200_for_business_plan(
    client: TestClient, db: Session
):
    """Business plan has churn_accuracy_card — expect 200."""
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.get(ORG_CARD_URL, headers=_headers(user))
    assert resp.status_code == 200


def test_get_accuracy_card_returns_active_model_metrics_for_org_with_calibration(
    client: TestClient, db: Session
):
    """When an active org model exists, metrics come from that model."""
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    model = _make_calibration_model(
        db,
        org.id,
        is_active=True,
        label_count=80,
        positive_count=20,
        f1=0.73,
        precision=0.76,
        recall=0.70,
        auc=0.82,
    )

    resp = client.get(ORG_CARD_URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["model_id"] == model.id
    assert body["label_count"] == 80
    assert body["positive_count"] == 20
    assert abs(body["f1"] - 0.73) < 0.001
    assert abs(body["precision"] - 0.76) < 0.001
    assert abs(body["recall"] - 0.70) < 0.001
    assert abs(body["auc"] - 0.82) < 0.001
    assert body["is_global_fallback"] is False


def test_get_accuracy_card_indicates_global_fallback_when_no_active_org_model(
    client: TestClient, db: Session
):
    """When org has no active model, fall back to global model and flag it."""
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    # Create global model (organization_id=None)
    global_model = _make_calibration_model(
        db, None, is_active=True, label_count=500, positive_count=100, f1=0.65
    )

    resp = client.get(ORG_CARD_URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["is_global_fallback"] is True
    assert body["model_id"] == global_model.id
    assert abs(body["f1"] - 0.65) < 0.001


def test_get_accuracy_card_history_contains_last_4_weeks_of_backtest_runs(
    client: TestClient, db: Session
):
    """History must contain at most 4 most recent backtest runs for the org."""
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    model = _make_calibration_model(db, org.id)

    # Create 6 runs — only 4 most recent should appear
    now = datetime.utcnow()
    for i in range(6):
        _make_backtest_run(
            db, org.id, model, run_at=now - timedelta(weeks=i), label_count=50 + i
        )

    resp = client.get(ORG_CARD_URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["history"]) == 4
    # Most recent first
    run_times = [r["run_at"] for r in body["history"]]
    assert run_times == sorted(run_times, reverse=True)


def test_get_accuracy_card_returns_null_metrics_when_no_model_ever_fitted(
    client: TestClient, db: Session
):
    """Fresh org with no calibrations anywhere — all metric fields null, is_global_fallback=True."""
    org = _make_org(db, plan="business")
    user = _make_user(db, org)

    resp = client.get(ORG_CARD_URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["model_id"] is None
    assert body["label_count"] == 0
    assert body["positive_count"] == 0
    assert body["precision"] is None
    assert body["recall"] is None
    assert body["f1"] is None
    assert body["auc"] is None
    assert body["fit_at"] is None
    assert body["is_global_fallback"] is True
    assert body["history"] == []


def test_get_accuracy_card_scoped_to_caller_org_only(
    client: TestClient, db: Session
):
    """Metrics are from the caller's org — not a different org's model."""
    org_a = _make_org(db, plan="business", name="OrgA")
    org_b = _make_org(db, plan="business", name="OrgB")
    user_a = _make_user(db, org_a)

    # Only org_b has an active model
    _make_calibration_model(db, org_b.id, is_active=True, label_count=100, f1=0.80)

    resp = client.get(ORG_CARD_URL, headers=_headers(user_a))
    assert resp.status_code == 200
    body = resp.json()

    # org_a has no model — must report null (global fallback, if any, or null)
    assert body["label_count"] == 0
    assert body["f1"] is None


# ===========================================================================
# System overview
# ===========================================================================


def test_get_system_accuracy_blocked_for_non_system_admin_returns_403(
    client: TestClient, db: Session
):
    """Regular users must get 403 on system accuracy endpoint."""
    org = _make_org(db, plan="business")
    user = _make_user(db, org, is_system_admin=False)
    resp = client.get(SYS_URL, headers=_headers(user))
    assert resp.status_code == 403


def test_get_system_accuracy_returns_200_for_system_admin(
    client: TestClient, db: Session
):
    """System admin must get 200."""
    org = _make_org(db, plan="business")
    admin = _make_user(db, org, is_system_admin=True)
    resp = client.get(SYS_URL, headers=_headers(admin))
    assert resp.status_code == 200


def test_get_system_accuracy_lists_orgs_with_calibration_data(
    client: TestClient, db: Session
):
    """Orgs that have at least one label must appear in the response."""
    org_a = _make_org(db, plan="business", name="Alpha")
    org_b = _make_org(db, plan="business", name="Beta")
    admin_org = _make_org(db, plan="enterprise", name="AdminOrg")
    admin = _make_user(db, admin_org, is_system_admin=True)

    _make_calibration_model(db, org_a.id, is_active=True, label_count=30)
    _make_calibration_model(db, org_b.id, is_active=True, label_count=15)

    resp = client.get(SYS_URL, headers=_headers(admin))
    assert resp.status_code == 200
    body = resp.json()

    org_ids = [row["organization_id"] for row in body["orgs"]]
    assert org_a.id in org_ids
    assert org_b.id in org_ids


def test_get_system_accuracy_excludes_orgs_with_zero_labels(
    client: TestClient, db: Session
):
    """Orgs with label_count=0 on their active model must not appear."""
    org_zero = _make_org(db, plan="business", name="ZeroLabels")
    org_has = _make_org(db, plan="business", name="HasLabels")
    admin_org = _make_org(db, plan="enterprise", name="AdminOrg")
    admin = _make_user(db, admin_org, is_system_admin=True)

    _make_calibration_model(db, org_zero.id, is_active=True, label_count=0)
    _make_calibration_model(db, org_has.id, is_active=True, label_count=25)

    resp = client.get(SYS_URL, headers=_headers(admin))
    assert resp.status_code == 200
    body = resp.json()

    org_ids = [row["organization_id"] for row in body["orgs"]]
    assert org_zero.id not in org_ids
    assert org_has.id in org_ids


def test_get_system_accuracy_orgs_sorted_by_label_count_desc(
    client: TestClient, db: Session
):
    """Org rows must be sorted by label_count descending."""
    admin_org = _make_org(db, plan="enterprise", name="AdminOrg")
    admin = _make_user(db, admin_org, is_system_admin=True)

    orgs_with_counts = [
        (_make_org(db, plan="business", name="Low"), 10),
        (_make_org(db, plan="business", name="High"), 200),
        (_make_org(db, plan="business", name="Mid"), 75),
    ]
    for org, lc in orgs_with_counts:
        _make_calibration_model(db, org.id, is_active=True, label_count=lc)

    resp = client.get(SYS_URL, headers=_headers(admin))
    assert resp.status_code == 200
    body = resp.json()

    counts = [r["label_count"] for r in body["orgs"]]
    assert counts == sorted(counts, reverse=True)


def test_get_system_accuracy_includes_global_model_summary(
    client: TestClient, db: Session
):
    """Response must carry global model fields when a global model exists."""
    admin_org = _make_org(db, plan="enterprise", name="AdminOrg")
    admin = _make_user(db, admin_org, is_system_admin=True)
    global_model = _make_calibration_model(
        db, None, is_active=True, label_count=1200, f1=0.68
    )

    resp = client.get(SYS_URL, headers=_headers(admin))
    assert resp.status_code == 200
    body = resp.json()

    assert body["global_model_id"] == global_model.id
    assert abs(body["global_f1"] - 0.68) < 0.001
    assert body["global_label_count"] == 1200


def test_get_system_accuracy_counts_orgs_using_global_vs_dedicated(
    client: TestClient, db: Session
):
    """total_orgs_using_global and total_orgs_with_dedicated_model must be correct."""
    admin_org = _make_org(db, plan="enterprise", name="AdminOrg")
    admin = _make_user(db, admin_org, is_system_admin=True)

    # Global model
    _make_calibration_model(db, None, is_active=True, label_count=500)
    # 2 orgs with dedicated models
    org_d1 = _make_org(db, plan="business", name="D1")
    org_d2 = _make_org(db, plan="business", name="D2")
    _make_calibration_model(db, org_d1.id, is_active=True, label_count=80)
    _make_calibration_model(db, org_d2.id, is_active=True, label_count=60)
    # 1 org with no model at all (uses global)
    org_no_model = _make_org(db, plan="business", name="NoModel")
    _make_user(db, org_no_model)

    resp = client.get(SYS_URL, headers=_headers(admin))
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_orgs_with_dedicated_model"] == 2
    # org_no_model has no active model so it uses global (but it has 0 labels,
    # so it won't appear in orgs list; the count still covers it)
    assert body["total_orgs_using_global"] >= 1


# ===========================================================================
# Per-org history
# ===========================================================================


def test_get_org_history_blocked_for_non_system_admin_returns_403(
    client: TestClient, db: Session
):
    """Non-system-admin must get 403 on per-org history."""
    org = _make_org(db, plan="business")
    user = _make_user(db, org, is_system_admin=False)
    resp = client.get(f"{SYS_URL}/{org.id}/history", headers=_headers(user))
    assert resp.status_code == 403


def test_get_org_history_returns_full_model_versions_list_newest_first(
    client: TestClient, db: Session
):
    """All model versions for the org must be returned, newest first."""
    admin_org = _make_org(db, plan="enterprise", name="AdminOrg")
    admin = _make_user(db, admin_org, is_system_admin=True)
    target_org = _make_org(db, plan="business", name="Target")

    now = datetime.utcnow()
    m_old = _make_calibration_model(
        db, target_org.id, is_active=False, label_count=10, fit_at=now - timedelta(weeks=4)
    )
    m_new = _make_calibration_model(
        db, target_org.id, is_active=True, label_count=50, fit_at=now
    )

    resp = client.get(f"{SYS_URL}/{target_org.id}/history", headers=_headers(admin))
    assert resp.status_code == 200
    body = resp.json()

    model_ids = [m["id"] for m in body["models"]]
    assert m_new.id in model_ids
    assert m_old.id in model_ids
    # Newest first
    fit_times = [m["fit_at"] for m in body["models"]]
    assert fit_times == sorted(fit_times, reverse=True)
    assert body["organization_id"] == target_org.id
    assert body["organization_name"] == target_org.name


def test_get_org_history_caps_backtest_runs_at_30(
    client: TestClient, db: Session
):
    """Only the last 30 backtest runs must be returned."""
    admin_org = _make_org(db, plan="enterprise", name="AdminOrg")
    admin = _make_user(db, admin_org, is_system_admin=True)
    target_org = _make_org(db, plan="business", name="Target")
    model = _make_calibration_model(db, target_org.id, is_active=True)

    now = datetime.utcnow()
    for i in range(35):
        _make_backtest_run(
            db, target_org.id, model, run_at=now - timedelta(days=i)
        )

    resp = client.get(f"{SYS_URL}/{target_org.id}/history", headers=_headers(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["backtest_runs"]) == 30


def test_get_org_history_404_for_unknown_org_id(
    client: TestClient, db: Session
):
    """Non-existent org_id must return 404."""
    admin_org = _make_org(db, plan="enterprise", name="AdminOrg")
    admin = _make_user(db, admin_org, is_system_admin=True)

    resp = client.get(f"{SYS_URL}/99999/history", headers=_headers(admin))
    assert resp.status_code == 404
