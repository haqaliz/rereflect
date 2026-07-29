"""
Tests for the "Batch Sentiment Alert" pre-built automation template
(batch-sentiment-trigger, Track A) — strict TDD (RED first).

Mirrors test_automation_template_usage_trend.py.

Covers:
  - GET /api/v1/automations/templates returns 7 templates including the new
    one.
  - The template's config passes TriggerSchema validation.
  - Enabling it creates a rule with trigger_type ==
    "batch_sentiment_threshold" and mode == "shadow" (never silently armed).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.routes.automations import TriggerSchema
from src.config.automation_templates import AUTOMATION_TEMPLATES, TEMPLATES_BY_ID
from src.models.organization import Organization

BATCH_SENTIMENT_TEMPLATE_ID = "batch_sentiment_alert"


# ---------------------------------------------------------------------------
# Template list
# ---------------------------------------------------------------------------


def test_templates_endpoint_includes_batch_sentiment_alert(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.get("/api/v1/automations/templates", headers=auth_headers)
    assert response.status_code == 200
    templates = response.json()

    ids = {t["id"] for t in templates}
    assert BATCH_SENTIMENT_TEMPLATE_ID in ids


def test_batch_sentiment_alert_present_in_config_module():
    assert BATCH_SENTIMENT_TEMPLATE_ID in TEMPLATES_BY_ID
    tmpl = TEMPLATES_BY_ID[BATCH_SENTIMENT_TEMPLATE_ID]
    assert tmpl["trigger"]["type"] == "batch_sentiment_threshold"
    assert tmpl["mode"] == "shadow"
    assert tmpl["cooldown_hours"] == 24


def test_batch_sentiment_alert_uses_send_notification_to_admins():
    tmpl = TEMPLATES_BY_ID[BATCH_SENTIMENT_TEMPLATE_ID]
    action_types = {a["type"] for a in tmpl["actions"]}
    assert "send_notification" in action_types
    notify = next(a for a in tmpl["actions"] if a["type"] == "send_notification")
    assert notify["config"]["recipients"] == "admins"
    assert set(notify["config"]["channels"]) == {"dashboard", "email"}


# ---------------------------------------------------------------------------
# The template's trigger config passes TriggerSchema validation
# ---------------------------------------------------------------------------


def test_batch_sentiment_alert_trigger_config_passes_trigger_schema():
    tmpl = TEMPLATES_BY_ID[BATCH_SENTIMENT_TEMPLATE_ID]
    # Must not raise — a template that ships a config the API would 422 on
    # is worse than no template at all.
    validated = TriggerSchema(**tmpl["trigger"])
    assert validated.type == "batch_sentiment_threshold"
    assert validated.config["sentiment"] in {"negative", "neutral", "positive"}
    assert validated.config["min_total"] >= 1


@pytest.mark.parametrize("tmpl", AUTOMATION_TEMPLATES, ids=lambda t: t["id"])
def test_every_template_trigger_config_passes_trigger_schema(tmpl):
    """Every template in AUTOMATION_TEMPLATES — new and pre-existing — must
    ship a trigger config the API would actually accept."""
    TriggerSchema(**tmpl["trigger"])


# ---------------------------------------------------------------------------
# Enabling the template creates a shadow-mode batch_sentiment_threshold rule
# ---------------------------------------------------------------------------


def test_enable_batch_sentiment_alert_creates_shadow_rule(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        f"/api/v1/automations/templates/{BATCH_SENTIMENT_TEMPLATE_ID}/enable",
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()

    assert body["template_id"] == BATCH_SENTIMENT_TEMPLATE_ID
    assert body["trigger"]["type"] == "batch_sentiment_threshold"
    assert body["mode"] == "shadow"
    # A rule in shadow mode is still "on" (evaluates + logs); is_active is the
    # derived off/not-off flag, mode is the source of truth.
    assert body["is_active"] is True
