"""
Tests for Automations API — batch_sentiment_threshold trigger config
validation (batch-sentiment-trigger, Track A) — strict TDD (RED first).

THE CONTRACT (docs/planning/batch-sentiment-trigger/trigger-core/spec.md):

    {
      "sentiment":    "negative",   // "negative" | "neutral" | "positive"
      "window_hours": 24,           // int, 1..168
      "mode":         "percentage", // "percentage" | "count"
      "threshold":    0.5,          // percentage: 0<x<=1. count: >=1
      "min_total":    5             // int >=1. Sample floor. NEVER 0.
    }
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _batch_sentiment_rule(config: dict | None = None) -> dict:
    base_config = {
        "sentiment": "negative",
        "window_hours": 24,
        "mode": "percentage",
        "threshold": 0.5,
        "min_total": 5,
    }
    if config:
        base_config.update(config)
    return {
        "name": "Batch Sentiment Alert",
        "trigger": {
            "type": "batch_sentiment_threshold",
            "config": base_config,
        },
        "actions": [
            {"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}},
        ],
        "cooldown_hours": 24,
    }


# ---------------------------------------------------------------------------
# Valid create -> 201
# ---------------------------------------------------------------------------

def test_create_rule_with_valid_batch_sentiment_config_succeeds(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations", json=_batch_sentiment_rule(), headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["trigger"]["type"] == "batch_sentiment_threshold"
    assert body["trigger"]["config"]["sentiment"] == "negative"
    assert body["trigger"]["config"]["window_hours"] == 24
    assert body["trigger"]["config"]["mode"] == "percentage"
    assert body["trigger"]["config"]["threshold"] == 0.5
    assert body["trigger"]["config"]["min_total"] == 5


def test_create_rule_with_valid_count_mode_config_succeeds(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"mode": "count", "threshold": 3}),
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["trigger"]["config"]["mode"] == "count"
    assert body["trigger"]["config"]["threshold"] == 3


# ---------------------------------------------------------------------------
# Invalid sentiment -> 422
# ---------------------------------------------------------------------------

def test_create_rule_with_invalid_sentiment_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"sentiment": "furious"}),
        headers=auth_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# window_hours out of range -> 422
# ---------------------------------------------------------------------------

def test_create_rule_with_window_hours_zero_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"window_hours": 0}),
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_create_rule_with_window_hours_too_large_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"window_hours": 169}),
        headers=auth_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Invalid mode -> 422
# ---------------------------------------------------------------------------

def test_create_rule_with_invalid_mode_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"mode": "ratio"}),
        headers=auth_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# min_total < 1 -> 422 (the sample floor must never be 0)
# ---------------------------------------------------------------------------

def test_create_rule_with_min_total_zero_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"min_total": 0}),
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_create_rule_with_min_total_negative_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"min_total": -1}),
        headers=auth_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# threshold <= 0 -> 422 (both modes)
# ---------------------------------------------------------------------------

def test_create_rule_with_threshold_zero_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"threshold": 0}),
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_create_rule_with_threshold_negative_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"mode": "count", "threshold": -3}),
        headers=auth_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# threshold > 1 rejected in percentage mode, but allowed in count mode
# ---------------------------------------------------------------------------

def test_create_rule_with_percentage_threshold_above_one_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"mode": "percentage", "threshold": 2.0}),
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_create_rule_with_count_threshold_above_one_accepted(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"mode": "count", "threshold": 10}),
        headers=auth_headers,
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Unknown extra config key -> 422 (proves extra: "forbid")
# ---------------------------------------------------------------------------

def test_create_rule_with_unknown_config_key_rejected(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        "/api/v1/automations",
        json=_batch_sentiment_rule({"unexpected_key": "value"}),
        headers=auth_headers,
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# trigger type registered in VALID_TRIGGER_TYPES
# ---------------------------------------------------------------------------

def test_batch_sentiment_threshold_is_a_valid_trigger_type():
    from src.api.routes.automations import VALID_TRIGGER_TYPES

    assert "batch_sentiment_threshold" in VALID_TRIGGER_TYPES
