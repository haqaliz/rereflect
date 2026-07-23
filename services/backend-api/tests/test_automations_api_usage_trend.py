"""
Tests for Automations API — usage_trend trigger config validation
(trigger-registration, Phase 3) — strict TDD (RED first).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usage_trend_rule(states: list, extra_config: dict | None = None) -> dict:
    config = {"states": states}
    if extra_config:
        config.update(extra_config)
    return {
        "name": "Usage Trend Alert",
        "trigger": {
            "type": "usage_trend",
            "config": config,
        },
        "actions": [
            {"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}},
        ],
        "cooldown_hours": 24,
    }


# ---------------------------------------------------------------------------
# AC6 — states: ["declining"] -> 201, response echoes the trigger
# ---------------------------------------------------------------------------

def test_create_rule_with_usage_trend_declining_succeeds(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations", json=_usage_trend_rule(["declining"]), headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["trigger"]["type"] == "usage_trend"
    assert body["trigger"]["config"]["states"] == ["declining"]


# ---------------------------------------------------------------------------
# states: ["declining", "sharp_decline"] -> 201
# ---------------------------------------------------------------------------

def test_create_rule_with_usage_trend_both_states_succeeds(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_usage_trend_rule(["declining", "sharp_decline"]),
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["trigger"]["config"]["states"] == ["declining", "sharp_decline"]


# ---------------------------------------------------------------------------
# states: [] -> 422
# ---------------------------------------------------------------------------

def test_create_rule_with_usage_trend_empty_states_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations", json=_usage_trend_rule([]), headers=auth_headers
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# states: ["stable"] -> 422 (cannot be entered as a worsening transition)
# ---------------------------------------------------------------------------

def test_create_rule_with_usage_trend_stable_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations", json=_usage_trend_rule(["stable"]), headers=auth_headers
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# states: ["insufficient_history"] -> 422
# ---------------------------------------------------------------------------

def test_create_rule_with_usage_trend_insufficient_history_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_usage_trend_rule(["insufficient_history"]),
        headers=auth_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# states: ["nonsense"] -> 422
# ---------------------------------------------------------------------------

def test_create_rule_with_usage_trend_nonsense_state_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations", json=_usage_trend_rule(["nonsense"]), headers=auth_headers
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Unknown extra config key -> 422 (strictness parity with sibling configs)
# ---------------------------------------------------------------------------

def test_create_rule_with_usage_trend_unknown_config_key_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_usage_trend_rule(["declining"], extra_config={"direction": "worsening"}),
        headers=auth_headers,
    )
    assert response.status_code == 422
