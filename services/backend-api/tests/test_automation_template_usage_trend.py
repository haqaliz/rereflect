"""
Tests for the "Usage Decline Outreach" pre-built automation template
(usage-trend-automation-trigger, template-and-docs aspect) — strict TDD.

Covers:
  AC1 — GET /api/v1/automations/templates returns 6 templates including the
        new one.
  AC2 — Enabling it creates a rule with trigger_type == "usage_trend", valid
        states, and mode == "shadow".
  AC3 — Enabling each of the 5 pre-existing templates still produces
        mode == "active" (regression test for the optional-`mode` change to
        `enable_template`).
  AC4 — The template's config passes `TriggerSchema` validation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.routes.automations import TriggerSchema
from src.config.automation_templates import AUTOMATION_TEMPLATES, TEMPLATES_BY_ID
from src.models.organization import Organization

USAGE_TEMPLATE_ID = "usage_decline_outreach"

PRE_EXISTING_TEMPLATE_IDS = [
    "churn_prevention",
    "critical_bug_escalation",
    "feature_request_triage",
    "negative_sentiment_alert",
    "positive_feedback_followup",
]


# ---------------------------------------------------------------------------
# AC1 — template list
# ---------------------------------------------------------------------------


def test_templates_endpoint_returns_six_including_usage_decline_outreach(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.get("/api/v1/automations/templates", headers=auth_headers)
    assert response.status_code == 200
    templates = response.json()
    assert len(templates) == 6

    ids = {t["id"] for t in templates}
    assert USAGE_TEMPLATE_ID in ids
    for tid in PRE_EXISTING_TEMPLATE_IDS:
        assert tid in ids


def test_usage_decline_outreach_present_in_config_module():
    assert USAGE_TEMPLATE_ID in TEMPLATES_BY_ID
    tmpl = TEMPLATES_BY_ID[USAGE_TEMPLATE_ID]
    assert tmpl["trigger"]["type"] == "usage_trend"


# ---------------------------------------------------------------------------
# Template action choice — send_notification, not run_playbook, and the
# description says why.
# ---------------------------------------------------------------------------


def test_usage_decline_outreach_uses_send_notification_not_run_playbook():
    tmpl = TEMPLATES_BY_ID[USAGE_TEMPLATE_ID]
    action_types = {a["type"] for a in tmpl["actions"]}
    assert action_types == {"send_notification"}
    assert "run_playbook" not in action_types

    # The description must tell the operator why, and that they should add a
    # playbook action themselves.
    description = tmpl["description"].lower()
    assert "playbook" in description


# ---------------------------------------------------------------------------
# AC4 — the template's trigger config passes TriggerSchema validation
# ---------------------------------------------------------------------------


def test_usage_decline_outreach_trigger_config_passes_trigger_schema():
    tmpl = TEMPLATES_BY_ID[USAGE_TEMPLATE_ID]
    # Must not raise — a template that ships a config the API would 422 on
    # is worse than no template at all.
    validated = TriggerSchema(**tmpl["trigger"])
    assert validated.type == "usage_trend"
    assert set(validated.config["states"]).issubset({"declining", "sharp_decline"})
    assert len(validated.config["states"]) >= 1


@pytest.mark.parametrize("tmpl", AUTOMATION_TEMPLATES, ids=lambda t: t["id"])
def test_every_template_trigger_config_passes_trigger_schema(tmpl):
    """Every template in AUTOMATION_TEMPLATES — new and pre-existing — must
    ship a trigger config the API would actually accept."""
    TriggerSchema(**tmpl["trigger"])


# ---------------------------------------------------------------------------
# AC2 — enabling the new template creates a shadow-mode usage_trend rule
# ---------------------------------------------------------------------------


def test_enable_usage_decline_outreach_creates_shadow_usage_trend_rule(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        f"/api/v1/automations/templates/{USAGE_TEMPLATE_ID}/enable",
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()

    assert body["template_id"] == USAGE_TEMPLATE_ID
    assert body["trigger"]["type"] == "usage_trend"
    assert set(body["trigger"]["config"]["states"]).issubset(
        {"declining", "sharp_decline"}
    )
    assert body["trigger"]["config"]["states"]  # non-empty
    assert body["mode"] == "shadow"
    # A rule in shadow mode is still "on" (evaluates + logs); is_active is the
    # derived off/not-off flag, mode is the source of truth.
    assert body["is_active"] is True


# ---------------------------------------------------------------------------
# AC3 — regression: the 5 pre-existing templates still produce mode=="active"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", PRE_EXISTING_TEMPLATE_IDS)
def test_enable_pre_existing_template_still_produces_active_mode(
    client: TestClient,
    db: Session,
    test_organization: Organization,
    auth_headers: dict,
    template_id: str,
):
    response = client.post(
        f"/api/v1/automations/templates/{template_id}/enable",
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["template_id"] == template_id
    assert body["mode"] == "active"
    assert body["is_active"] is True
