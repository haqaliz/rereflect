"""
Tests for the automation trigger→action support matrix (automation-action-support
R3/R4/R5) — strict TDD (RED first).

The matrix is pinned to a golden fixture shared with the worker-service suite so
the API and the worker executors can never disagree about which actions a
trigger can actually run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.churn_playbook import ChurnPlaybook
from src.models.organization import Organization

GOLDEN_PATH = (
    Path(__file__).resolve().parent
    / ".." / ".." / "worker-service" / "tests" / "fixtures"
    / "automation_action_support.json"
)


def _golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text())


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

NOTIFY = {"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}}
ASSIGN = {"type": "auto_assign", "config": {"assign_to": "round_robin"}}
STATUS = {"type": "change_status", "config": {"status": "in_review"}}
DRAFT = {"type": "draft_response", "config": {"tone": "empathetic"}}

TRIGGERS = {
    "usage_trend": {"type": "usage_trend", "config": {"states": ["declining"]}},
    "health_score_threshold": {
        "type": "health_score_threshold",
        "config": {"threshold": 30, "direction": "below"},
    },
    "feedback_category_match": {
        "type": "feedback_category_match",
        "config": {"categories": ["critical_bug"]},
    },
}


def _rule(trigger_key: str, actions: list) -> dict:
    return {
        "name": "Matrix rule",
        "trigger": TRIGGERS[trigger_key],
        "actions": actions,
        "cooldown_hours": 24,
    }


def _make_playbook(db: Session, org: Optional[Organization]) -> ChurnPlaybook:
    pb = ChurnPlaybook(
        organization_id=org.id if org else None,
        name="Matrix Playbook",
        probability_min=0.50,
        probability_max=0.70,
        action_sequence=[{"type": "send_notification", "config": {"message": "x"}}],
        is_template=False,
        is_active=True,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


# ---------------------------------------------------------------------------
# R3 — the constant
# ---------------------------------------------------------------------------

def test_matrix_equals_golden_fixture():
    from src.api.routes.automations import SUPPORTED_ACTIONS_BY_TRIGGER

    as_lists = {k: list(v) for k, v in SUPPORTED_ACTIONS_BY_TRIGGER.items()}
    assert as_lists == _golden()


def test_matrix_keys_equal_valid_trigger_types():
    from src.api.routes.automations import SUPPORTED_ACTIONS_BY_TRIGGER, VALID_TRIGGER_TYPES

    assert set(SUPPORTED_ACTIONS_BY_TRIGGER) == set(VALID_TRIGGER_TYPES)


def test_matrix_values_are_valid_action_types():
    from src.api.routes.automations import SUPPORTED_ACTIONS_BY_TRIGGER, VALID_ACTION_TYPES

    for actions in SUPPORTED_ACTIONS_BY_TRIGGER.values():
        assert set(actions) <= VALID_ACTION_TYPES


# ---------------------------------------------------------------------------
# R3 — create
# ---------------------------------------------------------------------------

def test_create_usage_trend_with_auto_assign_rejected(
    client: TestClient, test_organization: Organization, auth_headers: dict
):
    resp = client.post(
        "/api/v1/automations", json=_rule("usage_trend", [NOTIFY, ASSIGN]), headers=auth_headers
    )
    assert resp.status_code == 422
    detail = str(resp.json()["detail"])
    assert "usage_trend" in detail
    assert "auto_assign" in detail


def test_create_health_score_with_draft_response_rejected(
    client: TestClient, test_organization: Organization, auth_headers: dict
):
    resp = client.post(
        "/api/v1/automations", json=_rule("health_score_threshold", [DRAFT]), headers=auth_headers
    )
    assert resp.status_code == 422
    detail = str(resp.json()["detail"])
    assert "health_score_threshold" in detail
    assert "draft_response" in detail


def test_create_health_score_with_send_notification_ok(
    client: TestClient, test_organization: Organization, auth_headers: dict
):
    resp = client.post(
        "/api/v1/automations", json=_rule("health_score_threshold", [NOTIFY]), headers=auth_headers
    )
    assert resp.status_code == 201


def test_create_feedback_category_with_run_playbook_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    # A real, org-owned active playbook — so the 422 can only come from the matrix.
    pb = _make_playbook(db, test_organization)
    resp = client.post(
        "/api/v1/automations",
        json=_rule(
            "feedback_category_match",
            [{"type": "run_playbook", "config": {"playbook_id": pb.id}}],
        ),
        headers=auth_headers,
    )
    assert resp.status_code == 422
    detail = str(resp.json()["detail"])
    assert "feedback_category_match" in detail
    assert "run_playbook" in detail


# ---------------------------------------------------------------------------
# R3 — update validates the effective (trigger, actions) pair
# ---------------------------------------------------------------------------

def test_update_actions_to_unsupported_rejected(
    client: TestClient, test_organization: Organization, auth_headers: dict
):
    created = client.post(
        "/api/v1/automations", json=_rule("usage_trend", [NOTIFY]), headers=auth_headers
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    resp = client.put(
        f"/api/v1/automations/{rule_id}", json={"actions": [STATUS]}, headers=auth_headers
    )
    assert resp.status_code == 422
    detail = str(resp.json()["detail"])
    assert "usage_trend" in detail
    assert "change_status" in detail

    # rule unchanged
    got = client.get(f"/api/v1/automations/{rule_id}", headers=auth_headers).json()
    assert [a["type"] for a in got["actions"]] == ["send_notification"]


def test_update_trigger_only_validates_existing_actions(
    client: TestClient, test_organization: Organization, auth_headers: dict
):
    created = client.post(
        "/api/v1/automations",
        json=_rule("feedback_category_match", [ASSIGN, NOTIFY]),
        headers=auth_headers,
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    resp = client.put(
        f"/api/v1/automations/{rule_id}",
        json={"trigger": TRIGGERS["usage_trend"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    detail = str(resp.json()["detail"])
    assert "usage_trend" in detail
    assert "auto_assign" in detail

    got = client.get(f"/api/v1/automations/{rule_id}", headers=auth_headers).json()
    assert got["trigger"]["type"] == "feedback_category_match"


def test_update_supported_pair_ok(
    client: TestClient, test_organization: Organization, auth_headers: dict
):
    created = client.post(
        "/api/v1/automations", json=_rule("feedback_category_match", [NOTIFY]), headers=auth_headers
    )
    rule_id = created.json()["id"]
    resp = client.put(
        f"/api/v1/automations/{rule_id}",
        json={"trigger": TRIGGERS["usage_trend"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["trigger"]["type"] == "usage_trend"


def test_update_legacy_invalid_rule_without_touching_trigger_or_actions_ok(
    client: TestClient, test_organization: Organization, auth_headers: dict, db: Session
):
    """A rule saved before the matrix existed can still be renamed / paused."""
    created = client.post(
        "/api/v1/automations", json=_rule("usage_trend", [NOTIFY]), headers=auth_headers
    )
    rule_id = created.json()["id"]
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
    rule.actions = [ASSIGN]  # simulate a pre-matrix row with an unsupported combo
    db.commit()

    resp = client.put(
        f"/api/v1/automations/{rule_id}",
        json={"name": "Renamed legacy rule", "mode": "off"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed legacy rule"


# ---------------------------------------------------------------------------
# R4 — GET /action-support
# ---------------------------------------------------------------------------

def test_action_support_endpoint_returns_matrix(
    client: TestClient, test_organization: Organization, auth_headers: dict
):
    resp = client.get("/api/v1/automations/action-support", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == _golden()


def test_action_support_endpoint_requires_auth(client: TestClient):
    resp = client.get("/api/v1/automations/action-support")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# R5 — templates
# ---------------------------------------------------------------------------

def test_every_template_action_supported_by_its_trigger():
    from src.config.automation_templates import AUTOMATION_TEMPLATES

    golden = _golden()
    for tmpl in AUTOMATION_TEMPLATES:
        trig = tmpl["trigger"]["type"]
        for action in tmpl["actions"]:
            assert action["type"] in golden[trig], (
                f"template {tmpl['id']}: {trig} cannot run {action['type']}"
            )


def test_churn_prevention_template_is_notify_only_and_honest():
    from src.config.automation_templates import TEMPLATES_BY_ID

    tmpl = TEMPLATES_BY_ID["churn_prevention"]
    assert [a["type"] for a in tmpl["actions"]] == ["send_notification"]
    desc = tmpl["description"].lower()
    assert "assign" not in desc
    assert "draft" not in desc
    assert "response" not in desc
