"""
Tests for the "At-Risk Customer Outreach" pre-built automation template
(automation-send-customer-email, docs-and-templates aspect) — strict TDD.

Mirrors test_automation_template_batch_sentiment.py.

Covers:
  - The template exists, is shadow-mode, and carries one send_customer_email
    action.
  - Its trigger AND action configs pass the Pydantic schemas the API would
    apply. This matters more than usual here: `enable_template` instantiates
    the rule straight from the dict WITHOUT running TriggerSchema/ActionSchema,
    so a bad template would create a rule the API itself would have 422'd.
  - Enabling it creates a shadow rule (a template that silently armed itself
    would email real customers on the strength of a click).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.routes.automations import (
    VALID_ACTION_TYPES,
    ActionSchema,
    TriggerSchema,
)
from src.config.automation_templates import AUTOMATION_TEMPLATES, TEMPLATES_BY_ID
from src.models.organization import Organization

AT_RISK_TEMPLATE_ID = "at_risk_customer_outreach"


# ---------------------------------------------------------------------------
# Template shape
# ---------------------------------------------------------------------------


def test_templates_endpoint_includes_at_risk_customer_outreach(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.get("/api/v1/automations/templates", headers=auth_headers)
    assert response.status_code == 200
    ids = {t["id"] for t in response.json()}
    assert AT_RISK_TEMPLATE_ID in ids


def test_at_risk_customer_outreach_present_in_config_module():
    assert AT_RISK_TEMPLATE_ID in TEMPLATES_BY_ID
    tmpl = TEMPLATES_BY_ID[AT_RISK_TEMPLATE_ID]
    assert tmpl["trigger"]["type"] == "churn_probability_threshold"
    assert tmpl["trigger"]["config"] == {"threshold": 0.6, "direction": "above"}
    assert tmpl["mode"] == "shadow"
    assert tmpl["cooldown_hours"] == 24


def test_at_risk_customer_outreach_sends_the_re_engagement_template():
    tmpl = TEMPLATES_BY_ID[AT_RISK_TEMPLATE_ID]
    assert tmpl["actions"] == [
        {
            "type": "send_customer_email",
            "config": {"template": "re_engagement", "recipient": "customer"},
        }
    ]


# ---------------------------------------------------------------------------
# Schema validity — enable_template bypasses both validators
# ---------------------------------------------------------------------------


def test_at_risk_action_type_is_valid():
    tmpl = TEMPLATES_BY_ID[AT_RISK_TEMPLATE_ID]
    assert tmpl["actions"][0]["type"] in VALID_ACTION_TYPES


def test_at_risk_configs_pass_the_api_schemas():
    tmpl = TEMPLATES_BY_ID[AT_RISK_TEMPLATE_ID]
    validated_trigger = TriggerSchema(**tmpl["trigger"])
    assert validated_trigger.config["threshold"] == 0.6

    validated_action = ActionSchema(**tmpl["actions"][0])
    assert validated_action.config == {
        "template": "re_engagement",
        "recipient": "customer",
    }


@pytest.mark.parametrize("tmpl", AUTOMATION_TEMPLATES, ids=lambda t: t["id"])
def test_every_template_action_config_passes_action_schema(tmpl):
    """Every template — new and pre-existing — must ship action configs the
    API would accept. `enable_template` does not validate them, so nothing
    else catches a template that persists an unusable rule."""
    for action in tmpl["actions"]:
        ActionSchema(**action)


# ---------------------------------------------------------------------------
# Enable path
# ---------------------------------------------------------------------------


def test_enable_at_risk_customer_outreach_creates_shadow_rule(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
):
    response = client.post(
        f"/api/v1/automations/templates/{AT_RISK_TEMPLATE_ID}/enable",
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["mode"] == "shadow"
    assert body["is_active"] is True
    assert body["trigger"]["type"] == "churn_probability_threshold"
    assert body["actions"][0]["type"] == "send_customer_email"
    assert body["actions"][0]["config"]["template"] == "re_engagement"
