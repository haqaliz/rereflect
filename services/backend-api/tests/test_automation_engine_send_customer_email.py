"""
TDD tests for AutomationEngine — send_customer_email action
(automation-send-customer-email, action-core Phase C).

An automation rule can email the customer (or their CS owner) by rendering a
built-in outreach template, writing an `automation_email_deliveries` audit row
(`queued`) and enqueuing the worker task `tasks.outreach.send_automation_email`.

Every skip is LOUD: the action result carries an `error` string and nothing is
enqueued. The no-key path additionally leaves a `skipped` audit row so a
self-hoster can see the send never happened.

Run:
    cd services/backend-api && ./venv/bin/python -m pytest \
        tests/test_automation_engine_send_customer_email.py -v
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.automation_email_delivery import AutomationEmailDelivery
from src.models.automation_rule import AutomationRule
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User


CUSTOMER_EMAIL = "c@x.com"


@pytest.fixture(autouse=True)
def _email_configured():
    """Pin RESEND_API_KEY on.

    It is captured at import time (`email_service.py:14`), so a developer's
    local .env and a bare CI runner disagree — patch the module attribute so
    these tests assert behaviour, not the environment. The no-key test patches
    it back off.
    """
    with patch("src.services.email_service.RESEND_API_KEY", "test-key"):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(
    db: Session,
    org_id: int,
    actions: list,
    mode: str = "active",
    trigger_type: str = "health_score_threshold",
    trigger_config: dict | None = None,
    name: str = "Email Rule",
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name=name,
        trigger_type=trigger_type,
        trigger_config=trigger_config or {"threshold": 30, "direction": "below"},
        actions=actions,
        mode=mode,
        cooldown_hours=24,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _make_health(
    db: Session,
    org_id: int,
    *,
    email: str = CUSTOMER_EMAIL,
    customer_name: str | None = "Dana",
    is_archived: bool = False,
    cs_owner_user_id: int | None = None,
) -> CustomerHealth:
    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        customer_name=customer_name,
        health_score=20,
        is_archived=is_archived,
        cs_owner_user_id=cs_owner_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _fire(engine, org_id, context, trigger="health_score_threshold"):
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            return engine.evaluate(org_id, trigger, context)


def _context(**overrides) -> dict:
    ctx = {"health_score": 20, "customer_email": CUSTOMER_EMAIL, "feedback_id": None}
    ctx.update(overrides)
    return ctx


EMAIL_ACTION = {"type": "send_customer_email", "config": {"template": "re_engagement"}}


# ---------------------------------------------------------------------------
# 1. Happy path — delivery row queued + task dispatched
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_queues_delivery_and_dispatches(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    test_organization.product_name_display = "Acme"
    db.commit()
    _make_health(db, test_organization.id)
    _make_rule(db, test_organization.id, actions=[EMAIL_ACTION])

    results = _fire(AutomationEngine(db), test_organization.id, _context())

    assert len(results) == 1
    action_result = results[0]["actions"][0]
    assert action_result["type"] == "send_customer_email"
    assert action_result["error"] is None

    rows = db.query(AutomationEmailDelivery).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "queued"
    assert row.organization_id == test_organization.id
    assert row.to_email == CUSTOMER_EMAIL
    assert row.customer_email == CUSTOMER_EMAIL
    assert row.template_key == "re_engagement"
    assert "Dana" in row.body
    assert "Acme" in row.body
    assert row.subject
    assert row.reason is None

    assert action_result["result"] == {"status": "queued", "delivery_id": row.id}
    mock_app.send_task.assert_called_once_with(
        "tasks.outreach.send_automation_email", args=[row.id]
    )


# ---------------------------------------------------------------------------
# 2. cs_assignee recipient resolves the owner's email
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_cs_assignee_resolves_owner_email(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.api.auth import hash_password
    from src.services.automation_engine import AutomationEngine

    mock_get_celery_app.return_value = MagicMock()

    owner = User(
        email="owner@acme.test",
        password_hash=hash_password("pass1234"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    _make_health(db, test_organization.id, cs_owner_user_id=owner.id)
    _make_rule(
        db,
        test_organization.id,
        actions=[{
            "type": "send_customer_email",
            "config": {"template": "re_engagement", "recipient": "cs_assignee"},
        }],
    )

    results = _fire(AutomationEngine(db), test_organization.id, _context())

    assert results[0]["actions"][0]["error"] is None
    row = db.query(AutomationEmailDelivery).one()
    assert row.to_email == "owner@acme.test"
    assert row.customer_email == CUSTOMER_EMAIL
    assert row.status == "queued"


# ---------------------------------------------------------------------------
# 3. No RESEND_API_KEY → loud skip + skipped audit row, no dispatch
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_no_key_skips_loudly(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    _make_health(db, test_organization.id)
    _make_rule(db, test_organization.id, actions=[EMAIL_ACTION])

    # RESEND_API_KEY is captured at import time — patch the module attribute.
    with patch("src.services.email_service.RESEND_API_KEY", ""):
        results = _fire(AutomationEngine(db), test_organization.id, _context())

    assert results[0]["actions"][0]["error"] == "email not configured"
    assert results[0]["actions"][0]["result"] is None

    row = db.query(AutomationEmailDelivery).one()
    assert row.status == "skipped"
    assert row.reason == "email not configured"
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Org-wide trigger (no customer email / __org__ sentinel) → loud skip
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_org_wide_no_customer_email_skips_loudly(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    rule = _make_rule(db, test_organization.id, actions=[EMAIL_ACTION])
    engine = AutomationEngine(db)

    for ctx in ({"customer_email": ""}, {}, {"customer_email": "__org__"}):
        result = engine._execute_send_customer_email(
            EMAIL_ACTION["config"], ctx, rule
        )
        assert result["error"] == "no customer email (org-wide trigger)"
        assert result["result"] is None

    assert db.query(AutomationEmailDelivery).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Archived customer → loud skip
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_archived_customer_skips_loudly(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    _make_health(db, test_organization.id, is_archived=True)
    _make_rule(db, test_organization.id, actions=[EMAIL_ACTION])

    results = _fire(AutomationEngine(db), test_organization.id, _context())

    assert results[0]["actions"][0]["error"] == "customer archived"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 6. cs_assignee resolution failures are loud
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_cs_assignee_no_health_row_errors(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    _make_rule(
        db,
        test_organization.id,
        actions=[{
            "type": "send_customer_email",
            "config": {"template": "re_engagement", "recipient": "cs_assignee"},
        }],
    )

    results = _fire(AutomationEngine(db), test_organization.id, _context())

    assert results[0]["actions"][0]["error"] == "no health row for customer"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_app.send_task.assert_not_called()


@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_cs_assignee_no_owner_errors(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    _make_health(db, test_organization.id, cs_owner_user_id=None)
    _make_rule(
        db,
        test_organization.id,
        actions=[{
            "type": "send_customer_email",
            "config": {"template": "re_engagement", "recipient": "cs_assignee"},
        }],
    )

    results = _fire(AutomationEngine(db), test_organization.id, _context())

    assert results[0]["actions"][0]["error"] == "no CS owner assigned"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Unknown template key at execution time (enable_template bypasses the
#    ActionSchema validator) → loud error
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_unknown_template_key_errors(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    _make_health(db, test_organization.id)
    _make_rule(
        db,
        test_organization.id,
        actions=[{"type": "send_customer_email", "config": {"template": "nope"}}],
    )

    results = _fire(AutomationEngine(db), test_organization.id, _context())

    assert results[0]["actions"][0]["error"] == "unknown template key: nope"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 8. Default recipient is the customer; missing health row still sends
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_default_recipient_is_customer_without_health_row(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    _make_rule(db, test_organization.id, actions=[EMAIL_ACTION])

    results = _fire(AutomationEngine(db), test_organization.id, _context())

    assert results[0]["actions"][0]["error"] is None
    row = db.query(AutomationEmailDelivery).one()
    assert row.to_email == CUSTOMER_EMAIL
    assert row.status == "queued"
    mock_app.send_task.assert_called_once()


# ---------------------------------------------------------------------------
# 9. Shadow mode never writes a delivery row and never dispatches
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_shadow_mode_no_delivery(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    _make_health(db, test_organization.id)
    _make_rule(db, test_organization.id, actions=[EMAIL_ACTION], mode="shadow")

    _fire(AutomationEngine(db), test_organization.id, _context())

    assert db.query(AutomationEmailDelivery).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 10. Product-name fallback when the org has no display name
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_send_customer_email_render_falls_back_to_rereflect(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_get_celery_app.return_value = MagicMock()

    test_organization.product_name_display = None
    db.commit()
    _make_health(db, test_organization.id)
    _make_rule(
        db,
        test_organization.id,
        actions=[{
            "type": "send_customer_email",
            "config": {"template": "weekly_digest_entry", "recipient": "customer"},
        }],
    )

    _fire(AutomationEngine(db), test_organization.id, _context())

    row = db.query(AutomationEmailDelivery).one()
    assert "Rereflect" in row.body
    # weekly_digest_entry's subject carries {{PRODUCT_NAME}} — it must be
    # substituted too (render_outreach_template only renders the body).
    assert "{{PRODUCT_NAME}}" not in row.subject
    assert "Rereflect" in row.subject
