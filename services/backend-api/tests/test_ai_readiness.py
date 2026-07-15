"""
Tests for the AI training-readiness report (M5.0) — strict TDD.

Endpoint under test:
  GET /api/v1/analytics/ai-readiness — per-org, no-ML, read-only aggregation over
  FeedbackItem / AICorrection / CustomerChurnEvent.

Uses the self-contained test-helper pattern (`_make_org`, `_make_user`, `_headers`)
rather than the shared `test_organization`/`auth_headers` fixtures, because AC3
(cross-org isolation) needs two independent orgs.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.config.readiness_thresholds import CHURN_LABEL_TARGET, CORRECTION_VOLUME_TARGET
from src.models.ai_correction import AICorrection
from src.models.churn_event import CustomerChurnEvent
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User


URL = "/api/v1/analytics/ai-readiness"


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


def _make_feedback(db: Session, org: Organization, n: int = 1) -> None:
    for i in range(n):
        db.add(
            FeedbackItem(
                organization_id=org.id,
                text=f"feedback {i}",
                source="manual",
            )
        )
    db.commit()


def _make_correction(
    db: Session, org: Organization, correction_type: str, user: User = None
) -> AICorrection:
    correction = AICorrection(
        organization_id=org.id,
        user_id=user.id if user else None,
        correction_type=correction_type,
        entity_type="feedback_item",
        entity_id=1,
        signal="correction",
        original_value="a",
        corrected_value="b",
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)
    return correction


def _make_churn_event(
    db: Session,
    org: Organization,
    *,
    reason_code: str,
    source: str,
    recovered: bool = False,
    email: str = None,
    churned_at: datetime = None,
) -> CustomerChurnEvent:
    event = CustomerChurnEvent(
        organization_id=org.id,
        customer_email=email or f"cust-{datetime.utcnow().timestamp()}@example.com",
        churned_at=churned_at or datetime.utcnow(),
        reason_code=reason_code,
        source=source,
        recovered_at=datetime.utcnow() if recovered else None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# AC1 — empty org returns zeros
# ---------------------------------------------------------------------------


def test_empty_org_returns_zeros(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["feedback_volume"] == 0
    assert body["corrections_total"] == 0
    assert body["corrections_by_type"] == {}
    assert body["churn_labels_total"] == 0
    assert body["churn_labels_recovered"] == 0
    assert body["churn_labels_by_reason"] == {}
    assert body["churn_labels_by_source"] == {}
    assert body["correction_volume_ready"] is False
    assert body["churn_labels_ready"] is False
    assert body["correction_volume_target"] == CORRECTION_VOLUME_TARGET
    assert body["churn_label_target"] == CHURN_LABEL_TARGET


# ---------------------------------------------------------------------------
# AC2 — mixed data returns exact counts
# ---------------------------------------------------------------------------


def test_mixed_data_returns_exact_counts(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)

    _make_feedback(db, org, n=7)

    _make_correction(db, org, "sentiment", user)
    _make_correction(db, org, "sentiment", user)
    _make_correction(db, org, "sentiment", user)
    _make_correction(db, org, "category", user)
    _make_correction(db, org, "category", user)
    _make_correction(db, org, "churn_risk", user)

    _make_churn_event(db, org, reason_code="price", source="manual", email="a@example.com")
    _make_churn_event(db, org, reason_code="price", source="manual", email="b@example.com")
    _make_churn_event(
        db, org, reason_code="competitor", source="csv_import", email="c@example.com"
    )
    _make_churn_event(
        db,
        org,
        reason_code="other",
        source="auto_suggested",
        recovered=True,
        email="d@example.com",
    )

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["feedback_volume"] == 7
    assert body["corrections_total"] == 6
    assert body["corrections_by_type"] == {"sentiment": 3, "category": 2, "churn_risk": 1}
    assert body["churn_labels_total"] == 4
    assert body["churn_labels_recovered"] == 1
    assert body["churn_labels_by_reason"] == {"price": 2, "competitor": 1, "other": 1}
    assert body["churn_labels_by_source"] == {
        "manual": 2,
        "csv_import": 1,
        "auto_suggested": 1,
    }


# ---------------------------------------------------------------------------
# AC3 — cross-org isolation
# ---------------------------------------------------------------------------


def test_cross_org_isolation(client: TestClient, db: Session):
    org_a = _make_org(db, name="OrgA")
    org_b = _make_org(db, name="OrgB")
    user_a = _make_user(db, org_a)
    user_b = _make_user(db, org_b)

    _make_feedback(db, org_a, n=3)
    _make_correction(db, org_a, "sentiment", user_a)
    _make_churn_event(
        db, org_a, reason_code="price", source="manual", email="orga-cust@example.com"
    )

    _make_feedback(db, org_b, n=9)
    _make_correction(db, org_b, "category", user_b)
    _make_correction(db, org_b, "category", user_b)
    _make_churn_event(
        db,
        org_b,
        reason_code="competitor",
        source="csv_import",
        email="orgb-cust@example.com",
    )
    _make_churn_event(
        db,
        org_b,
        reason_code="competitor",
        source="csv_import",
        email="orgb-cust2@example.com",
    )

    resp_a = client.get(URL, headers=_headers(user_a))
    assert resp_a.status_code == 200
    body_a = resp_a.json()
    assert body_a["feedback_volume"] == 3
    assert body_a["corrections_total"] == 1
    assert body_a["corrections_by_type"] == {"sentiment": 1}
    assert "category" not in body_a["corrections_by_type"]
    assert body_a["churn_labels_total"] == 1
    assert body_a["churn_labels_by_reason"] == {"price": 1}
    assert "competitor" not in body_a["churn_labels_by_reason"]

    resp_b = client.get(URL, headers=_headers(user_b))
    assert resp_b.status_code == 200
    body_b = resp_b.json()
    assert body_b["feedback_volume"] == 9
    assert body_b["corrections_total"] == 2
    assert body_b["corrections_by_type"] == {"category": 2}
    assert "sentiment" not in body_b["corrections_by_type"]
    assert body_b["churn_labels_total"] == 2
    assert body_b["churn_labels_by_reason"] == {"competitor": 2}
    assert "price" not in body_b["churn_labels_by_reason"]


# ---------------------------------------------------------------------------
# AC4 — correction volume ready-flag boundary (inclusive >=)
# ---------------------------------------------------------------------------


def test_correction_volume_ready_boundary(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)

    for _ in range(CORRECTION_VOLUME_TARGET - 1):
        _make_correction(db, org, "sentiment", user)

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["corrections_total"] == CORRECTION_VOLUME_TARGET - 1
    assert body["correction_volume_ready"] is False

    _make_correction(db, org, "sentiment", user)

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["corrections_total"] == CORRECTION_VOLUME_TARGET
    assert body["correction_volume_ready"] is True


# ---------------------------------------------------------------------------
# AC5 — churn label ready-flag boundary (inclusive >=)
# ---------------------------------------------------------------------------


def test_churn_labels_ready_boundary(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)

    base_date = datetime.utcnow()
    for i in range(CHURN_LABEL_TARGET - 1):
        _make_churn_event(
            db,
            org,
            reason_code="other",
            source="manual",
            email=f"cust{i}@example.com",
            churned_at=base_date - timedelta(days=i),
        )

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["churn_labels_total"] == CHURN_LABEL_TARGET - 1
    assert body["churn_labels_ready"] is False

    _make_churn_event(
        db,
        org,
        reason_code="other",
        source="manual",
        email="cust-last@example.com",
        churned_at=base_date - timedelta(days=CHURN_LABEL_TARGET),
    )

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["churn_labels_total"] == CHURN_LABEL_TARGET
    assert body["churn_labels_ready"] is True


# ---------------------------------------------------------------------------
# AC6 — recovered churn events still count as labels
# ---------------------------------------------------------------------------


def test_recovered_churn_event_still_counts(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)

    _make_churn_event(
        db,
        org,
        reason_code="price",
        source="manual",
        recovered=True,
        email="recovered@example.com",
    )

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["churn_labels_total"] == 1
    assert body["churn_labels_recovered"] == 1
    assert body["churn_labels_by_reason"] == {"price": 1}
    assert body["churn_labels_by_source"] == {"manual": 1}


# ---------------------------------------------------------------------------
# AC7 — auth required, any role can view
# ---------------------------------------------------------------------------


def test_requires_auth(client: TestClient):
    resp = client.get(URL)
    # No Authorization header at all -> HTTPBearer's own 403 (this repo's
    # established convention — see test_ai_corrections.py's *_requires_auth tests).
    assert resp.status_code == 403


def test_member_role_can_view(client: TestClient, db: Session):
    org = _make_org(db)
    member = _make_user(db, org, role="member")

    _make_feedback(db, org, n=2)
    _make_correction(db, org, "sentiment", member)

    resp = client.get(URL, headers=_headers(member))
    assert resp.status_code == 200
    body = resp.json()
    assert body["feedback_volume"] == 2
    assert body["corrections_total"] == 1


# ---------------------------------------------------------------------------
# readiness-honesty (crm-churn-labels, wave 2) — churn_labels_trainable
#
# The calibrator excludes source='auto_suggested' in four places
# (worker-service/src/tasks/churn_calibration.py:50,125,
# worker-service/src/services/calibration_refit.py:64,191). These tests pin
# the report to agree with the fit: `churn_labels_ready` must gate on
# `churn_labels_trainable`, never on `churn_labels_total`.
# ---------------------------------------------------------------------------


def test_trainable_excludes_auto_suggested_at_boundary(client: TestClient, db: Session):
    """AC-1 (the regression test). 499 manual + 5 auto_suggested must NOT be ready."""
    org = _make_org(db)
    user = _make_user(db, org)

    for i in range(CHURN_LABEL_TARGET - 1):
        _make_churn_event(
            db, org, reason_code="other", source="manual", email=f"m{i}@example.com"
        )
    for i in range(5):
        _make_churn_event(
            db, org, reason_code="other", source="auto_suggested", email=f"a{i}@example.com"
        )

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["churn_labels_total"] == CHURN_LABEL_TARGET - 1 + 5
    assert body["churn_labels_trainable"] == CHURN_LABEL_TARGET - 1
    assert body["churn_labels_ready"] is False


def test_trainable_ready_at_target_with_auto_present(client: TestClient, db: Session):
    """AC-1. 500 manual + 1 auto_suggested -> trainable==500, ready True."""
    org = _make_org(db)
    user = _make_user(db, org)

    for i in range(CHURN_LABEL_TARGET):
        _make_churn_event(
            db, org, reason_code="other", source="manual", email=f"m{i}@example.com"
        )
    _make_churn_event(db, org, reason_code="other", source="auto_suggested", email="a@example.com")

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["churn_labels_trainable"] == CHURN_LABEL_TARGET
    assert body["churn_labels_ready"] is True


def test_trainable_counts_manual_and_csv_import(client: TestClient, db: Session):
    """AC-3. manual and csv_import both count as trainable; only auto_suggested excluded."""
    org = _make_org(db)
    user = _make_user(db, org)

    _make_churn_event(db, org, reason_code="price", source="manual", email="m@example.com")
    _make_churn_event(db, org, reason_code="price", source="csv_import", email="c@example.com")
    _make_churn_event(db, org, reason_code="price", source="auto_suggested", email="au@example.com")

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["churn_labels_total"] == 3
    assert body["churn_labels_trainable"] == 2


def test_recovered_event_still_trainable(client: TestClient, db: Session):
    """AC-4. A recovered event with a trainable source counts in total, its bucket, AND trainable."""
    org = _make_org(db)
    user = _make_user(db, org)

    _make_churn_event(
        db,
        org,
        reason_code="price",
        source="manual",
        recovered=True,
        email="recovered@example.com",
    )

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["churn_labels_total"] == 1
    assert body["churn_labels_by_source"] == {"manual": 1}
    assert body["churn_labels_trainable"] == 1


def test_trainable_org_scoped(client: TestClient, db: Session):
    """AC-7. Another org's trainable events contribute 0."""
    org_a = _make_org(db, name="TrainA")
    org_b = _make_org(db, name="TrainB")
    user_a = _make_user(db, org_a)
    user_b = _make_user(db, org_b)

    _make_churn_event(db, org_a, reason_code="price", source="manual", email="a@example.com")
    _make_churn_event(db, org_b, reason_code="price", source="manual", email="b1@example.com")
    _make_churn_event(db, org_b, reason_code="price", source="csv_import", email="b2@example.com")

    resp_a = client.get(URL, headers=_headers(user_a))
    assert resp_a.json()["churn_labels_trainable"] == 1

    resp_b = client.get(URL, headers=_headers(user_b))
    assert resp_b.json()["churn_labels_trainable"] == 2
