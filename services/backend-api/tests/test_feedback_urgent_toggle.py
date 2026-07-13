"""
TDD tests for the internal urgent-toggle endpoint —
PATCH /api/v1/feedback/{id}/urgent (capture-seam Phase 2).

Coverage:
  - value change -> 200, is_urgent flips, exactly one
    AICorrection(correction_type="urgency", signal="correction",
    corrected_value="urgent"/"not_urgent", user_id=<acting user>).
  - no-op (same value) -> 200, zero corrections.
  - cross-org id -> 404, no side effect.
  - unauthenticated -> 401/403.
  - R-5 (critical): the analyzer heuristic set (feedback.py:112) and the
    re-analyze clear (update_feedback, feedback.py:665) are analyzer-driven
    and must NOT emit urgency corrections.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.ai_correction import AICorrection
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User


def _other_org_admin_token(db: Session) -> str:
    """Create a second organization + admin user, return their JWT."""
    org = Organization(name="Rival Inc", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        email="rival-admin@example.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return create_access_token({
        "user_id": user.id,
        "organization_id": org.id,
        "role": "admin",
    })


class TestUrgentToggleValueChange:
    def test_toggle_to_urgent_flips_flag_and_records_correction(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        test_user: User,
        test_feedback: FeedbackItem,
    ):
        assert test_feedback.is_urgent is False

        resp = client.patch(
            f"/api/v1/feedback/{test_feedback.id}/urgent",
            json={"is_urgent": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_urgent"] is True

        db.refresh(test_feedback)
        assert test_feedback.is_urgent is True

        corrections = (
            db.query(AICorrection)
            .filter(AICorrection.correction_type == "urgency")
            .all()
        )
        assert len(corrections) == 1
        c = corrections[0]
        assert c.organization_id == test_organization.id
        assert c.user_id == test_user.id
        assert c.entity_type == "feedback_item"
        assert c.entity_id == test_feedback.id
        assert c.signal == "correction"
        assert c.original_value == "not_urgent"
        assert c.corrected_value == "urgent"
        assert c.feedback_text == test_feedback.text

    def test_toggle_to_not_urgent_flips_flag_and_records_correction(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        fb = FeedbackItem(
            organization_id=test_organization.id,
            text="Everything is on fire, help!",
            source="email",
            is_urgent=True,
        )
        db.add(fb)
        db.commit()
        db.refresh(fb)

        resp = client.patch(
            f"/api/v1/feedback/{fb.id}/urgent",
            json={"is_urgent": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_urgent"] is False

        corrections = (
            db.query(AICorrection)
            .filter(AICorrection.correction_type == "urgency")
            .all()
        )
        assert len(corrections) == 1
        assert corrections[0].original_value == "urgent"
        assert corrections[0].corrected_value == "not_urgent"
        assert corrections[0].user_id == test_user.id


class TestUrgentToggleNoOp:
    def test_same_value_emits_no_correction(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_feedback: FeedbackItem,
    ):
        assert test_feedback.is_urgent is False

        resp = client.patch(
            f"/api/v1/feedback/{test_feedback.id}/urgent",
            json={"is_urgent": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_urgent"] is False

        corrections = (
            db.query(AICorrection)
            .filter(AICorrection.correction_type == "urgency")
            .all()
        )
        assert corrections == []


class TestUrgentToggleCrossOrg:
    def test_cross_org_id_404_no_side_effect(
        self,
        client: TestClient,
        db: Session,
        test_feedback: FeedbackItem,
    ):
        other_token = _other_org_admin_token(db)
        headers = {"Authorization": f"Bearer {other_token}"}

        resp = client.patch(
            f"/api/v1/feedback/{test_feedback.id}/urgent",
            json={"is_urgent": True},
            headers=headers,
        )
        assert resp.status_code == 404

        db.refresh(test_feedback)
        assert test_feedback.is_urgent is False

        corrections = db.query(AICorrection).all()
        assert corrections == []


class TestUrgentToggleAuth:
    def test_requires_auth(self, client: TestClient, test_feedback: FeedbackItem):
        resp = client.patch(
            f"/api/v1/feedback/{test_feedback.id}/urgent",
            json={"is_urgent": True},
        )
        assert resp.status_code in (401, 403)


class TestUrgentToggleAnalyzerDoesNotEmitCorrections:
    """R-5 (critical): analyzer-driven is_urgent changes must never create an
    urgency AICorrection — only user-driven changes via this endpoint (or the
    public API) may."""

    def test_analyze_single_feedback_heuristic_set_emits_zero_corrections(
        self,
        db: Session,
        test_organization: Organization,
    ):
        """feedback.py:112 — the create-time heuristic set of is_urgent must
        not touch AICorrection, even when it flips is_urgent to True."""
        from src.api.routes.feedback import analyze_single_feedback

        fb = FeedbackItem(
            organization_id=test_organization.id,
            text=(
                "This is urgent! The system is completely broken and "
                "crashing constantly, I cannot access anything."
            ),
            source="email",
        )
        db.add(fb)
        db.commit()
        db.refresh(fb)

        analyze_single_feedback(fb, db)
        db.refresh(fb)

        corrections = (
            db.query(AICorrection)
            .filter(AICorrection.correction_type == "urgency")
            .all()
        )
        assert corrections == []

    def test_text_edit_patch_reanalyze_emits_zero_urgency_corrections(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_feedback: FeedbackItem,
    ):
        """update_feedback (feedback.py:636) clears is_urgent to False then
        re-analyzes (feedback.py:665) — analyzer-driven, must not emit."""
        resp = client.patch(
            f"/api/v1/feedback/{test_feedback.id}",
            headers=auth_headers,
            json={
                "text": (
                    "This is urgent! Everything is broken and crashing, "
                    "cannot log in at all."
                ),
                "source": "email",
            },
        )
        assert resp.status_code == 200, resp.text

        corrections = (
            db.query(AICorrection)
            .filter(AICorrection.correction_type == "urgency")
            .all()
        )
        assert corrections == []
