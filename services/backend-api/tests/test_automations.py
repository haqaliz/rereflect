"""
Tests for AI Workflow Automation API (M4.4) — Phase 1.

TDD: tests written before implementation.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_org(db: Session, plan: str = "pro") -> Organization:
    org = Organization(name=f"TestOrg-{plan}", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"{role}-{org.id}@example.com",
        password_hash=hash_password("pass1234"),
        organization_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _token(user: User) -> dict:
    token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# Minimal valid payloads
HEALTH_SCORE_RULE = {
    "name": "Churn Alert",
    "trigger": {
        "type": "health_score_threshold",
        "config": {"threshold": 30, "direction": "below"},
    },
    "actions": [
        {"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}},
    ],
    "cooldown_hours": 24,
}

SENTIMENT_RULE = {
    "name": "Negative Spike",
    "trigger": {
        "type": "sentiment_pattern",
        "config": {"count": 3, "days": 7, "sentiment": "negative"},
    },
    "actions": [
        {"type": "change_status", "config": {"status": "in_review"}},
    ],
    "cooldown_hours": 48,
}


# ---------------------------------------------------------------------------
# 1. test_list_rules_empty
# ---------------------------------------------------------------------------

def test_list_rules_empty(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    response = client.get("/api/v1/automations", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["rules"] == []
    assert body["total"] == 0
    assert "limit" in body


# ---------------------------------------------------------------------------
# 2. test_create_rule_with_health_score_trigger
# ---------------------------------------------------------------------------

def test_create_rule_with_health_score_trigger(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    response = client.post("/api/v1/automations", json=HEALTH_SCORE_RULE, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Churn Alert"
    assert body["trigger"]["type"] == "health_score_threshold"
    assert body["trigger"]["config"]["threshold"] == 30
    assert body["is_active"] is True
    assert body["execution_count"] == 0


# ---------------------------------------------------------------------------
# 3. test_create_rule_with_sentiment_pattern_trigger
# ---------------------------------------------------------------------------

def test_create_rule_with_sentiment_pattern_trigger(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    response = client.post("/api/v1/automations", json=SENTIMENT_RULE, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["trigger"]["type"] == "sentiment_pattern"
    assert body["trigger"]["config"]["count"] == 3
    assert body["trigger"]["config"]["days"] == 7


# ---------------------------------------------------------------------------
# 4. test_create_rule_with_multiple_actions
# ---------------------------------------------------------------------------

def test_create_rule_with_multiple_actions(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    payload = {
        "name": "Multi-Action Rule",
        "trigger": {
            "type": "churn_risk_level_change",
            "config": {"target_level": "critical"},
        },
        "actions": [
            {"type": "auto_assign", "config": {"assign_to": "role:admin"}},
            {"type": "change_status", "config": {"status": "in_review"}},
            {"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard", "email"]}},
            {"type": "draft_response", "config": {"tone": "empathetic"}},
        ],
        "cooldown_hours": 24,
    }
    response = client.post("/api/v1/automations", json=payload, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert len(body["actions"]) == 4


# ---------------------------------------------------------------------------
# 5. test_create_rule_validates_trigger_config
# ---------------------------------------------------------------------------

def test_create_rule_validates_trigger_config(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    # threshold out of range
    bad_threshold = {
        "name": "Bad Rule",
        "trigger": {
            "type": "health_score_threshold",
            "config": {"threshold": 150, "direction": "below"},
        },
        "actions": [{"type": "change_status", "config": {"status": "in_review"}}],
        "cooldown_hours": 24,
    }
    r = client.post("/api/v1/automations", json=bad_threshold, headers=auth_headers)
    assert r.status_code == 422

    # direction must be "below"
    bad_direction = {
        "name": "Bad Rule 2",
        "trigger": {
            "type": "health_score_threshold",
            "config": {"threshold": 30, "direction": "above"},
        },
        "actions": [{"type": "change_status", "config": {"status": "in_review"}}],
        "cooldown_hours": 24,
    }
    r = client.post("/api/v1/automations", json=bad_direction, headers=auth_headers)
    assert r.status_code == 422

    # churn_risk_level_change: invalid target_level
    bad_level = {
        "name": "Bad Rule 3",
        "trigger": {
            "type": "churn_risk_level_change",
            "config": {"target_level": "zombie"},
        },
        "actions": [{"type": "change_status", "config": {"status": "in_review"}}],
        "cooldown_hours": 24,
    }
    r = client.post("/api/v1/automations", json=bad_level, headers=auth_headers)
    assert r.status_code == 422

    # feedback_category_match: empty categories
    bad_categories = {
        "name": "Bad Rule 4",
        "trigger": {
            "type": "feedback_category_match",
            "config": {"categories": []},
        },
        "actions": [{"type": "change_status", "config": {"status": "in_review"}}],
        "cooldown_hours": 24,
    }
    r = client.post("/api/v1/automations", json=bad_categories, headers=auth_headers)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 6. test_create_rule_validates_action_config
# ---------------------------------------------------------------------------

def test_create_rule_validates_action_config(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    # invalid action type
    bad_action_type = {
        "name": "Bad Action Rule",
        "trigger": {
            "type": "health_score_threshold",
            "config": {"threshold": 30, "direction": "below"},
        },
        "actions": [{"type": "send_email_blast", "config": {}}],
        "cooldown_hours": 24,
    }
    r = client.post("/api/v1/automations", json=bad_action_type, headers=auth_headers)
    assert r.status_code == 422

    # change_status: missing status
    bad_status_config = {
        "name": "Bad Status Rule",
        "trigger": {
            "type": "health_score_threshold",
            "config": {"threshold": 30, "direction": "below"},
        },
        "actions": [{"type": "change_status", "config": {}}],
        "cooldown_hours": 24,
    }
    r = client.post("/api/v1/automations", json=bad_status_config, headers=auth_headers)
    assert r.status_code == 422

    # change_status: invalid status value
    bad_status_value = {
        "name": "Bad Status Value Rule",
        "trigger": {
            "type": "health_score_threshold",
            "config": {"threshold": 30, "direction": "below"},
        },
        "actions": [{"type": "change_status", "config": {"status": "deleted"}}],
        "cooldown_hours": 24,
    }
    r = client.post("/api/v1/automations", json=bad_status_value, headers=auth_headers)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 7. test_create_rule_enforces_plan_limit
# ---------------------------------------------------------------------------

def test_create_rule_enforces_plan_limit(client: TestClient, db: Session, auth_headers: dict, test_organization: Organization, test_user: User):
    # test_organization is on "pro" plan (limit 5)
    # Create 5 rules
    for i in range(5):
        payload = {**HEALTH_SCORE_RULE, "name": f"Rule {i}"}
        r = client.post("/api/v1/automations", json=payload, headers=auth_headers)
        assert r.status_code == 201, f"Expected 201 on rule {i}, got {r.status_code}"

    # 6th should fail with 402 or 403
    payload = {**HEALTH_SCORE_RULE, "name": "Rule 6 (over limit)"}
    r = client.post("/api/v1/automations", json=payload, headers=auth_headers)
    assert r.status_code in (402, 403)


# ---------------------------------------------------------------------------
# 8. test_get_rule_by_id
# ---------------------------------------------------------------------------

def test_get_rule_by_id(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    create_resp = client.post("/api/v1/automations", json=HEALTH_SCORE_RULE, headers=auth_headers)
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/v1/automations/{rule_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["id"] == rule_id
    assert body["name"] == "Churn Alert"


# ---------------------------------------------------------------------------
# 9. test_update_rule
# ---------------------------------------------------------------------------

def test_update_rule(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    create_resp = client.post("/api/v1/automations", json=HEALTH_SCORE_RULE, headers=auth_headers)
    rule_id = create_resp.json()["id"]

    update_payload = {"name": "Updated Rule Name", "cooldown_hours": 48}
    put_resp = client.put(f"/api/v1/automations/{rule_id}", json=update_payload, headers=auth_headers)
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert body["name"] == "Updated Rule Name"
    assert body["cooldown_hours"] == 48


# ---------------------------------------------------------------------------
# 10. test_delete_rule
# ---------------------------------------------------------------------------

def test_delete_rule(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    create_resp = client.post("/api/v1/automations", json=HEALTH_SCORE_RULE, headers=auth_headers)
    rule_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/api/v1/automations/{rule_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    get_resp = client.get(f"/api/v1/automations/{rule_id}", headers=auth_headers)
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# 11. test_toggle_rule_pause_resume
# ---------------------------------------------------------------------------

def test_toggle_rule_pause_resume(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    create_resp = client.post("/api/v1/automations", json=HEALTH_SCORE_RULE, headers=auth_headers)
    rule_id = create_resp.json()["id"]
    assert create_resp.json()["is_active"] is True

    # Pause
    patch_resp = client.patch(f"/api/v1/automations/{rule_id}/toggle", headers=auth_headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    # Resume
    patch_resp2 = client.patch(f"/api/v1/automations/{rule_id}/toggle", headers=auth_headers)
    assert patch_resp2.status_code == 200
    assert patch_resp2.json()["is_active"] is True


# ---------------------------------------------------------------------------
# 12. test_list_templates
# ---------------------------------------------------------------------------

def test_list_templates(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    response = client.get("/api/v1/automations/templates", headers=auth_headers)
    assert response.status_code == 200
    templates = response.json()
    assert isinstance(templates, list)
    # 5 original (M4.4) + 1 (M10, usage-trend-automation-trigger)
    assert len(templates) == 6

    ids = {t["id"] for t in templates}
    assert "churn_prevention" in ids
    assert "critical_bug_escalation" in ids
    assert "feature_request_triage" in ids
    assert "negative_sentiment_alert" in ids
    assert "positive_feedback_followup" in ids
    assert "usage_decline_outreach" in ids


# ---------------------------------------------------------------------------
# 13. test_enable_template_creates_rule
# ---------------------------------------------------------------------------

def test_enable_template_creates_rule(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    response = client.post(
        "/api/v1/automations/templates/churn_prevention/enable",
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["template_id"] == "churn_prevention"
    assert body["is_active"] is True
    assert body["trigger"]["type"] == "health_score_threshold"

    # Should appear in list
    list_resp = client.get("/api/v1/automations", headers=auth_headers)
    assert list_resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# 14. test_execution_log_empty
# ---------------------------------------------------------------------------

def test_execution_log_empty(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    create_resp = client.post("/api/v1/automations", json=HEALTH_SCORE_RULE, headers=auth_headers)
    rule_id = create_resp.json()["id"]

    log_resp = client.get(f"/api/v1/automations/{rule_id}/executions", headers=auth_headers)
    assert log_resp.status_code == 200
    assert log_resp.json() == []


# ---------------------------------------------------------------------------
# 15. test_member_cannot_create_rule
# ---------------------------------------------------------------------------

def test_member_cannot_create_rule(client: TestClient, db: Session, test_organization: Organization):
    member = _make_user(db, test_organization, role="member")
    headers = _token(member)

    response = client.post("/api/v1/automations", json=HEALTH_SCORE_RULE, headers=headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 16. test_free_plan_cannot_create_rule
# ---------------------------------------------------------------------------

def test_free_plan_cannot_create_rule(client: TestClient, db: Session):
    free_org = _make_org(db, plan="free")
    admin = _make_user(db, free_org, role="admin")
    headers = _token(admin)

    response = client.post("/api/v1/automations", json=HEALTH_SCORE_RULE, headers=headers)
    assert response.status_code in (402, 403)


# ---------------------------------------------------------------------------
# 17. test_cooldown_validation
# ---------------------------------------------------------------------------

def test_cooldown_validation(client: TestClient, db: Session, test_organization: Organization, auth_headers: dict):
    # cooldown_hours below minimum (< 1)
    bad_low = {**HEALTH_SCORE_RULE, "cooldown_hours": 0}
    r = client.post("/api/v1/automations", json=bad_low, headers=auth_headers)
    assert r.status_code == 422

    # cooldown_hours above maximum (> 168)
    bad_high = {**HEALTH_SCORE_RULE, "cooldown_hours": 200}
    r = client.post("/api/v1/automations", json=bad_high, headers=auth_headers)
    assert r.status_code == 422

    # valid boundary values
    min_payload = {**HEALTH_SCORE_RULE, "name": "Min Cooldown", "cooldown_hours": 1}
    r = client.post("/api/v1/automations", json=min_payload, headers=auth_headers)
    assert r.status_code == 201

    max_payload = {**HEALTH_SCORE_RULE, "name": "Max Cooldown", "cooldown_hours": 168}
    r = client.post("/api/v1/automations", json=max_payload, headers=auth_headers)
    assert r.status_code == 201
