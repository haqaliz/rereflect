"""
Tests for Automations API — churn_probability_threshold trigger, run_playbook
action, and `mode` (M4.4 churn-triggered-playbooks, Task 5) — strict TDD (RED first).
"""

from __future__ import annotations

from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.churn_playbook import ChurnPlaybook
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_org(db: Session, plan: str = "pro") -> Organization:
    org = Organization(name=f"ChurnAutoOrg-{plan}-{id(plan)}", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"user-{org.id}-{role}@churnauto.test",
        password_hash=hash_password("pass1234"),
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


def _make_playbook(
    db: Session,
    org: Optional[Organization] = None,
    name: str = "Test Playbook",
    is_active: bool = True,
) -> ChurnPlaybook:
    pb = ChurnPlaybook(
        organization_id=org.id if org else None,
        name=name,
        probability_min=0.50,
        probability_max=0.70,
        action_sequence=[{"type": "send_notification", "config": {"message": "test"}}],
        is_template=False,
        is_active=is_active,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


def _churn_trigger_rule(threshold: float = 0.7, direction: str = "above") -> dict:
    return {
        "name": "Churn Risk Alert",
        "trigger": {
            "type": "churn_probability_threshold",
            "config": {"threshold": threshold, "direction": direction},
        },
        "actions": [
            {"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}},
        ],
        "cooldown_hours": 24,
    }


def _run_playbook_rule(playbook_id: int, mode: Optional[str] = None) -> dict:
    payload = {
        "name": "Run Playbook Rule",
        "trigger": {
            "type": "health_score_threshold",
            "config": {"threshold": 30, "direction": "below"},
        },
        "actions": [
            {"type": "run_playbook", "config": {"playbook_id": playbook_id}},
        ],
        "cooldown_hours": 24,
    }
    if mode is not None:
        payload["mode"] = mode
    return payload


# ---------------------------------------------------------------------------
# 1. Create rule with churn_probability_threshold trigger
# ---------------------------------------------------------------------------

def test_create_rule_with_churn_probability_trigger(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post("/api/v1/automations", json=_churn_trigger_rule(), headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["trigger"]["type"] == "churn_probability_threshold"
    assert body["trigger"]["config"]["threshold"] == 0.7
    assert body["trigger"]["config"]["direction"] == "above"
    assert body["mode"] == "active"


# ---------------------------------------------------------------------------
# 2. threshold out of range -> 422
# ---------------------------------------------------------------------------

def test_create_rule_churn_threshold_out_of_range(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations", json=_churn_trigger_rule(threshold=1.5), headers=auth_headers
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 3. direction != "above" -> 422
# ---------------------------------------------------------------------------

def test_create_rule_churn_direction_invalid(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations", json=_churn_trigger_rule(direction="below"), headers=auth_headers
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. run_playbook referencing an org-owned active playbook -> OK
# ---------------------------------------------------------------------------

def test_create_rule_with_run_playbook_action_org_owned(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    playbook = _make_playbook(db, org=test_organization)
    response = client.post(
        "/api/v1/automations", json=_run_playbook_rule(playbook.id), headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["actions"][0]["type"] == "run_playbook"
    assert body["actions"][0]["config"]["playbook_id"] == playbook.id


def test_create_rule_with_run_playbook_action_template_playbook(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    # organization_id=None is a system template, allowed for any org.
    playbook = _make_playbook(db, org=None)
    response = client.post(
        "/api/v1/automations", json=_run_playbook_rule(playbook.id), headers=auth_headers
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# 5. run_playbook referencing missing / other-org / inactive playbook -> 422
# ---------------------------------------------------------------------------

def test_create_rule_run_playbook_missing_playbook(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations", json=_run_playbook_rule(999999), headers=auth_headers
    )
    assert response.status_code == 422
    assert "run_playbook" in response.json()["detail"]


def test_create_rule_run_playbook_other_org(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    other_org = _make_org(db, plan="pro")
    playbook = _make_playbook(db, org=other_org)
    response = client.post(
        "/api/v1/automations", json=_run_playbook_rule(playbook.id), headers=auth_headers
    )
    assert response.status_code == 422


def test_create_rule_run_playbook_inactive(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    playbook = _make_playbook(db, org=test_organization, is_active=False)
    response = client.post(
        "/api/v1/automations", json=_run_playbook_rule(playbook.id), headers=auth_headers
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 6. mode="shadow" -> persists, is_active True
# ---------------------------------------------------------------------------

def test_create_rule_with_mode_shadow(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    payload = _churn_trigger_rule()
    payload["mode"] = "shadow"
    response = client.post("/api/v1/automations", json=payload, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "shadow"
    assert body["is_active"] is True


# ---------------------------------------------------------------------------
# 7. mode="off" -> is_active False; invalid mode -> 422
# ---------------------------------------------------------------------------

def test_create_rule_with_mode_off(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    payload = _churn_trigger_rule()
    payload["mode"] = "off"
    response = client.post("/api/v1/automations", json=payload, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "off"
    assert body["is_active"] is False


def test_create_rule_with_invalid_mode(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    payload = _churn_trigger_rule()
    payload["mode"] = "paused"
    response = client.post("/api/v1/automations", json=payload, headers=auth_headers)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 8. Update rule's mode shadow -> active persists
# ---------------------------------------------------------------------------

def test_update_rule_mode_shadow_to_active(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    payload = _churn_trigger_rule()
    payload["mode"] = "shadow"
    create_resp = client.post("/api/v1/automations", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/v1/automations/{rule_id}", json={"mode": "active"}, headers=auth_headers
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["mode"] == "active"
    assert body["is_active"] is True


def test_update_rule_invalid_mode_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    create_resp = client.post("/api/v1/automations", json=_churn_trigger_rule(), headers=auth_headers)
    rule_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/v1/automations/{rule_id}", json={"mode": "paused"}, headers=auth_headers
    )
    assert update_resp.status_code == 422


def test_update_rule_run_playbook_action_validates_ownership(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    create_resp = client.post("/api/v1/automations", json=_churn_trigger_rule(), headers=auth_headers)
    rule_id = create_resp.json()["id"]

    other_org = _make_org(db, plan="pro")
    other_playbook = _make_playbook(db, org=other_org)

    update_resp = client.put(
        f"/api/v1/automations/{rule_id}",
        json={"actions": [{"type": "run_playbook", "config": {"playbook_id": other_playbook.id}}]},
        headers=auth_headers,
    )
    assert update_resp.status_code == 422


# ---------------------------------------------------------------------------
# 9. Non-admin/owner caller rejected
# ---------------------------------------------------------------------------

def test_member_cannot_create_rule_with_churn_trigger(
    client: TestClient, db: Session, test_organization: Organization
):
    member = _make_user(db, test_organization, role="member")
    headers = _headers(member)

    response = client.post("/api/v1/automations", json=_churn_trigger_rule(), headers=headers)
    assert response.status_code == 403
