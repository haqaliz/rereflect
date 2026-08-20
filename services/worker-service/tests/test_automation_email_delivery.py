"""
Tests for the worker mirror of `automation_email_deliveries` + the shared
send_customer_email helper (automation-send-customer-email, worker-mirrors
aspect, Phase 1 + Phase 5).

Strict TDD: written FIRST (RED) before the mirror + helpers.

The column-set test is the CROSS-PROCESS SEAM PIN: the worker cannot import
backend-api, so nothing but this assertion keeps the mirror honest when the
backend model (`services/backend-api/src/models/automation_email_delivery.py`)
changes.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import AutomationEmailDelivery, Base, CustomerHealth, Organization, User
from src.models.automation_rule import AutomationRule


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


from src.services.automation_email_delivery import (  # noqa: E402
    AUTOMATION_EMAIL_TASK_NAME,
    create_delivery_row,
    execute_send_customer_email,
    get_delivery_row,
    set_delivery_outcome,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _make_org(db, org_id=1, product_name=None) -> Organization:
    org = Organization(id=org_id, name="Acme", plan="pro",
                       product_name_display=product_name)
    db.add(org)
    db.commit()
    return org


def _make_rule(db, org_id=1, actions=None, trigger_type="feedback_category_match"):
    rule = AutomationRule(
        organization_id=org_id,
        name="Email rule",
        trigger_type=trigger_type,
        trigger_config={},
        actions=actions or [],
        cooldown_hours=24,
        mode="active",
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _make_health(db, org_id=1, email="cust@example.com", name="Dana",
                 is_archived=False, cs_owner_user_id=None) -> CustomerHealth:
    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        customer_name=name,
        health_score=20,
        is_archived=is_archived,
        cs_owner_user_id=cs_owner_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_user(db, org_id=1, email="owner@acme.test") -> User:
    user = User(email=email, organization_id=org_id, role="owner")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


CONFIG = {"template": "re_engagement", "recipient": "customer"}


# ---------------------------------------------------------------------------
# 1. Model mirror parity (cross-process seam pin)
# ---------------------------------------------------------------------------

def test_model_mirror_table_and_columns():
    table = Base.metadata.tables["automation_email_deliveries"]
    assert set(table.columns.keys()) == {
        "id",
        "organization_id",
        "rule_id",
        "customer_email",
        "to_email",
        "template_key",
        "subject",
        "body",
        "status",
        "reason",
        "created_at",
        "updated_at",
    }


def test_task_name_constant_matches_backend_dispatch_string():
    # Byte-identical to the backend engine's send_task(...) string.
    assert AUTOMATION_EMAIL_TASK_NAME == "tasks.outreach.send_automation_email"


def test_registered_task_name_matches_the_constant():
    """The seam pin: the registered Celery task name, the constant the mirrors
    document, and the backend's dispatch string are all one string. A drift
    here enqueues work nothing will ever run."""
    from src.tasks.outreach import send_automation_email as task

    assert task.name == AUTOMATION_EMAIL_TASK_NAME


# ---------------------------------------------------------------------------
# 2. Row helpers
# ---------------------------------------------------------------------------

def test_create_delivery_row_inserts_queued_row(db):
    row = create_delivery_row(
        db,
        org_id=1,
        rule_id=7,
        customer_email="cust@example.com",
        to_email="cust@example.com",
        template_key="re_engagement",
        subject="Hi",
        body="Body",
    )
    assert row.id is not None
    assert row.status == "queued"
    assert row.reason is None
    db.commit()

    fetched = get_delivery_row(db, row.id)
    assert fetched is not None
    assert fetched.template_key == "re_engagement"
    assert fetched.body == "Body"


def test_get_delivery_row_missing_returns_none(db):
    assert get_delivery_row(db, 999) is None


def test_set_delivery_outcome_persists(db):
    row = create_delivery_row(
        db, org_id=1, rule_id=7, customer_email="c@x.com", to_email="c@x.com",
        template_key="re_engagement", subject="Hi", body="Body",
    )
    db.commit()

    set_delivery_outcome(db, row, "skipped", "opted out")

    fetched = get_delivery_row(db, row.id)
    assert fetched.status == "skipped"
    assert fetched.reason == "opted out"


# ---------------------------------------------------------------------------
# 3. Shared handler — happy paths
# ---------------------------------------------------------------------------

@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_queues_and_dispatches(mock_task, db):
    _make_org(db, product_name="Acme")
    rule = _make_rule(db)
    _make_health(db)

    with patch("src.email.RESEND_API_KEY", "test-key"):
        result = execute_send_customer_email(
            CONFIG, rule, "cust@example.com", db
        )

    row = db.query(AutomationEmailDelivery).one()
    assert row.status == "queued"
    assert row.to_email == "cust@example.com"
    assert row.customer_email == "cust@example.com"
    assert row.template_key == "re_engagement"
    assert "Dana" in row.body
    assert "Acme" in row.body
    assert "{{PRODUCT_NAME}}" not in row.subject

    assert result == {
        "type": "send_customer_email",
        "result": {"status": "queued", "delivery_id": row.id},
        "error": None,
    }
    mock_task.delay.assert_called_once_with(row.id)


@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_cs_assignee_resolves_owner(mock_task, db):
    _make_org(db)
    owner = _make_user(db)
    rule = _make_rule(db)
    _make_health(db, cs_owner_user_id=owner.id)

    with patch("src.email.RESEND_API_KEY", "test-key"):
        result = execute_send_customer_email(
            {"template": "re_engagement", "recipient": "cs_assignee"},
            rule, "cust@example.com", db,
        )

    assert result["error"] is None
    row = db.query(AutomationEmailDelivery).one()
    assert row.to_email == "owner@acme.test"
    assert row.customer_email == "cust@example.com"


@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_product_name_falls_back(mock_task, db):
    _make_org(db, product_name=None)
    rule = _make_rule(db)
    _make_health(db)

    with patch("src.email.RESEND_API_KEY", "test-key"):
        execute_send_customer_email(
            {"template": "weekly_digest_entry", "recipient": "customer"},
            rule, "cust@example.com", db,
        )

    row = db.query(AutomationEmailDelivery).one()
    assert "Rereflect" in row.subject
    assert "Rereflect" in row.body


@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_missing_health_row_still_sends(mock_task, db):
    _make_org(db)
    rule = _make_rule(db)

    with patch("src.email.RESEND_API_KEY", "test-key"):
        result = execute_send_customer_email(CONFIG, rule, "cust@example.com", db)

    assert result["error"] is None
    row = db.query(AutomationEmailDelivery).one()
    assert row.to_email == "cust@example.com"
    mock_task.delay.assert_called_once()


@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_broker_down_still_reports_queued(mock_task, db):
    _make_org(db)
    rule = _make_rule(db)
    mock_task.delay.side_effect = RuntimeError("broker down")

    with patch("src.email.RESEND_API_KEY", "test-key"):
        result = execute_send_customer_email(CONFIG, rule, "cust@example.com", db)

    # Honest "work accepted, outcome unknown": the row stays queued, the
    # action does not claim success it cannot verify... but it is not an error
    # on the evaluator either — the delivery row is the audit trail.
    assert result["result"]["status"] == "queued"
    assert db.query(AutomationEmailDelivery).one().status == "queued"


# ---------------------------------------------------------------------------
# 4. Shared handler — every skip is loud
# ---------------------------------------------------------------------------

@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_no_key_is_loud(mock_task, db):
    _make_org(db)
    rule = _make_rule(db)
    _make_health(db)

    with patch("src.email.RESEND_API_KEY", ""):
        result = execute_send_customer_email(CONFIG, rule, "cust@example.com", db)

    assert result["error"] == "email not configured"
    assert result["result"] is None
    row = db.query(AutomationEmailDelivery).one()
    assert row.status == "skipped"
    assert row.reason == "email not configured"
    mock_task.delay.assert_not_called()


@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_no_customer_email_is_loud(mock_task, db):
    _make_org(db)
    rule = _make_rule(db)

    with patch("src.email.RESEND_API_KEY", "test-key"):
        for email in ("", None, "__org__"):
            result = execute_send_customer_email(CONFIG, rule, email, db)
            assert result["error"] == "no customer email (org-wide trigger)"

    assert db.query(AutomationEmailDelivery).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_archived_is_loud(mock_task, db):
    _make_org(db)
    rule = _make_rule(db)
    _make_health(db, is_archived=True)

    with patch("src.email.RESEND_API_KEY", "test-key"):
        result = execute_send_customer_email(CONFIG, rule, "cust@example.com", db)

    assert result["error"] == "customer archived"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_cs_assignee_failures_are_loud(mock_task, db):
    _make_org(db)
    rule = _make_rule(db)
    cfg = {"template": "re_engagement", "recipient": "cs_assignee"}

    with patch("src.email.RESEND_API_KEY", "test-key"):
        # a. no health row
        assert execute_send_customer_email(cfg, rule, "cust@example.com", db)["error"] \
            == "no health row for customer"

        # b. health row without an owner
        health = _make_health(db)
        assert execute_send_customer_email(cfg, rule, "cust@example.com", db)["error"] \
            == "no CS owner assigned"

        # c. owner id pointing at a missing user
        health.cs_owner_user_id = 4242
        db.commit()
        assert execute_send_customer_email(cfg, rule, "cust@example.com", db)["error"] \
            == "CS owner has no email"

    assert db.query(AutomationEmailDelivery).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_email_delivery.send_automation_email")
def test_execute_send_customer_email_bad_config_is_loud(mock_task, db):
    _make_org(db)
    rule = _make_rule(db)
    _make_health(db)

    with patch("src.email.RESEND_API_KEY", "test-key"):
        assert execute_send_customer_email({}, rule, "cust@example.com", db)["error"] \
            == "unknown template key: None"
        assert execute_send_customer_email(
            {"template": "nope"}, rule, "cust@example.com", db
        )["error"] == "unknown template key: nope"
        assert execute_send_customer_email(
            {"template": "re_engagement", "recipient": "boss"}, rule,
            "cust@example.com", db,
        )["error"] == "unsupported recipient: boss"

    assert db.query(AutomationEmailDelivery).count() == 0
    mock_task.delay.assert_not_called()
