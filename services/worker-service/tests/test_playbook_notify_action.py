"""
Tests for the `notify` playbook action — playbook_engine._handle_notify
(tag-notify-actions aspect, M2).

TDD: written RED-first — every test fails with
`unsupported action type: 'notify'` until the handler lands.

Channels: slack / discord (external sends to the org's connected
Integration rows via the tasks.alerts senders, wrapped — they RAISE) and
dashboard (in-app Notification rows via the notification_dispatch
dispatch_alert seam, honoring UserAlertPreference).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    CustomerHealth,
    Integration,
    Notification,
    Organization,
    User,
    UserAlertPreference,
    ChurnPlaybook,
    ChurnPlaybookExecution,
)

# ---------------------------------------------------------------------------
# In-memory DB wiring (same pattern as test_playbook_engine.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helper builders (copied from test_playbook_engine.py fixture pattern)
# ---------------------------------------------------------------------------

def _make_org(db) -> Organization:
    org = Organization(name="Test Org", plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_playbook(db, org_id: int, action_sequence=None) -> ChurnPlaybook:
    pb = ChurnPlaybook(
        organization_id=org_id,
        name="Test Playbook",
        description="A test playbook",
        probability_min="0.50",
        probability_max="0.85",
        action_sequence=action_sequence or [
            {"type": "notify", "config": {"channel": "slack", "message": "hi"}},
        ],
        is_template=False,
        is_active=True,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


def _make_execution(
    db,
    playbook_id: int,
    org_id: int,
    customer_email: str = "customer@example.com",
    status: str = "queued",
) -> ChurnPlaybookExecution:
    exe = ChurnPlaybookExecution(
        playbook_id=playbook_id,
        organization_id=org_id,
        customer_email=customer_email,
        triggered_by="manual",
        status=status,
        action_log=[],
        created_at=datetime.utcnow(),
    )
    db.add(exe)
    db.commit()
    db.refresh(exe)
    return exe


def _make_health(db, org_id: int, email: str = "customer@example.com") -> CustomerHealth:
    health = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        health_score=40,
        churn_risk_component=70,
        sentiment_component=30,
        resolution_component=40,
        frequency_component=50,
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


def _make_user(db, org_id: int, role: str, email: str) -> User:
    user = User(email=email, organization_id=org_id, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_integration(db, org_id: int, integ_type: str, config: dict) -> Integration:
    integ = Integration(
        organization_id=org_id,
        type=integ_type,
        name=f"{integ_type} integration",
        config=config,
        is_active=True,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _build_run(db, org_id: int, config: dict, email: str = "customer@example.com"):
    pb = _make_playbook(db, org_id, action_sequence=[
        {"type": "notify", "config": config},
    ])
    _make_health(db, org_id, email=email)
    return _make_execution(db, pb.id, org_id, customer_email=email, status="queued")


def _execute(db, exe):
    from src.services import playbook_engine
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    return db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()


# ---------------------------------------------------------------------------
# AC4 — slack
# ---------------------------------------------------------------------------

def _recording_slack_sender():
    calls = []

    def fake(webhook_url=None, blocks=None, text=None):
        calls.append({"webhook_url": webhook_url, "blocks": blocks, "text": text})
        return {"success": True}

    return fake, calls


def test_notify_slack_sends_to_each_active_integration(db, monkeypatch):
    """AC4: one call per active Slack integration; result records the channel
    and the advisory target."""
    org = _make_org(db)
    _make_integration(db, org.id, "slack", {"webhook_url": "https://hooks.slack.com/a"})
    _make_integration(db, org.id, "slack", {"webhook_url": "https://hooks.slack.com/b"})
    fake, calls = _recording_slack_sender()
    monkeypatch.setattr("src.tasks.alerts.send_slack_message_webhook", fake)

    exe = _build_run(db, org.id, {
        "channel": "slack", "target": "#cs-leads", "message": "Customer at risk.",
    })
    updated = _execute(db, exe)

    assert len(calls) == 2
    assert {c["webhook_url"] for c in calls} == {
        "https://hooks.slack.com/a", "https://hooks.slack.com/b",
    }
    assert "Customer at risk." in calls[0]["blocks"][0]["text"]["text"]
    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"] == {
        "channel": "slack",
        "integrations_sent": 2,
        "target": "#cs-leads",
    }
    assert updated.status == "done"


def test_notify_slack_raising_sender_is_ok_false_run_completes(db, monkeypatch):
    """AC4: the Slack sender RAISES → ok=False with the exception message;
    the run still finalizes (no crash)."""
    org = _make_org(db)
    _make_integration(db, org.id, "slack", {"webhook_url": "https://hooks.slack.com/a"})

    def boom(**kwargs):
        raise RuntimeError("slack exploded")

    monkeypatch.setattr("src.tasks.alerts.send_slack_message_webhook", boom)

    exe = _build_run(db, org.id, {"channel": "slack", "message": "hi"})
    updated = _execute(db, exe)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "slack exploded" in entry["error"]
    assert entry["result"]["integrations_sent"] == 0
    assert updated.completed_at is not None


def test_notify_slack_ignores_inactive_integrations(db, monkeypatch):
    """AC4: inactive Slack integrations are not sent to; none active → ok=False."""
    org = _make_org(db)
    _make_integration(db, org.id, "slack", {"webhook_url": "https://hooks.slack.com/a"})
    db.query(Integration).filter_by(organization_id=org.id).update(
        {Integration.is_active: False}
    )
    db.commit()
    fake, calls = _recording_slack_sender()
    monkeypatch.setattr("src.tasks.alerts.send_slack_message_webhook", fake)

    exe = _build_run(db, org.id, {"channel": "slack", "message": "hi"})
    updated = _execute(db, exe)

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "no slack" in entry["error"].lower()


# ---------------------------------------------------------------------------
# AC5 — discord
# ---------------------------------------------------------------------------

def test_notify_discord_sends_to_active_discord_integration(db, monkeypatch):
    """AC5: the Discord sender is called with content + embeds for the org's
    active Discord integration."""
    org = _make_org(db)
    _make_integration(db, org.id, "discord", {"webhook_url": "https://discord.com/api/webhooks/1/abc"})
    calls = []

    def fake(webhook_url=None, embeds=None, content=None):
        calls.append({"webhook_url": webhook_url, "embeds": embeds, "content": content})
        return {"success": True}

    monkeypatch.setattr("src.tasks.alerts.send_discord_message_webhook", fake)

    exe = _build_run(db, org.id, {"channel": "discord", "message": "Customer at risk."})
    updated = _execute(db, exe)

    assert len(calls) == 1
    assert calls[0]["webhook_url"] == "https://discord.com/api/webhooks/1/abc"
    assert calls[0]["content"] == "Customer at risk."
    assert calls[0]["embeds"][0]["description"] == "Customer at risk."
    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"]["channel"] == "discord"
    assert entry["result"]["integrations_sent"] == 1


def test_notify_discord_no_integration_is_loud_failure(db, monkeypatch):
    """AC5: no active Discord integration → ok=False with a specific reason."""
    org = _make_org(db)
    calls = []

    def fake(webhook_url=None, embeds=None, content=None):
        calls.append(webhook_url)
        return {"success": True}

    monkeypatch.setattr("src.tasks.alerts.send_discord_message_webhook", fake)

    exe = _build_run(db, org.id, {"channel": "discord", "message": "hi"})
    updated = _execute(db, exe)

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "no discord" in entry["error"].lower()


# ---------------------------------------------------------------------------
# AC6 — dashboard (dispatch_alert seam, preferences honored)
# ---------------------------------------------------------------------------

def _point_dispatch_session_at(monkeypatch, db):
    """House pattern (test_discord_dispatch.py): make notification_dispatch's
    get_db_session context yield the test session."""
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = db
    mock_ctx.__exit__.return_value = False
    monkeypatch.setattr("src.notification_dispatch.get_db_session", lambda: mock_ctx)


def test_notify_dashboard_creates_notifications_for_enabled_users(db, monkeypatch):
    """AC6: Notification rows are created via dispatch_alert for users whose
    UserAlertPreference has channel_inapp on; opted-out users are skipped;
    result reports the created count."""
    org = _make_org(db)
    enabled = _make_user(db, org.id, "admin", "on@example.com")
    opted = _make_user(db, org.id, "admin", "off@example.com")
    db.add(UserAlertPreference(
        user_id=opted.id, alert_type="churn_risk",
        is_enabled=True, channel_inapp=False,
    ))
    db.commit()
    _point_dispatch_session_at(monkeypatch, db)

    exe = _build_run(db, org.id, {"channel": "dashboard", "message": "Follow up with this customer."})
    updated = _execute(db, exe)

    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"] == {"notifications_created": 1}

    notifs = db.query(Notification).all()
    assert len(notifs) == 1
    assert notifs[0].user_id == enabled.id
    assert notifs[0].organization_id == org.id
    assert notifs[0].type == "churn_risk"
    assert notifs[0].message == "Follow up with this customer."
    assert updated.status == "done"


def test_notify_dashboard_defaults_create_notification(db, monkeypatch):
    """AC6: a user with no preference row falls back to defaults (enabled,
    channel_inapp on) and still gets a Notification."""
    org = _make_org(db)
    _make_user(db, org.id, "owner", "default@example.com")
    _point_dispatch_session_at(monkeypatch, db)

    exe = _build_run(db, org.id, {"channel": "dashboard", "message": "hi"})
    updated = _execute(db, exe)

    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"] == {"notifications_created": 1}
    assert db.query(Notification).count() == 1


# ---------------------------------------------------------------------------
# AC7 — loud failures: no integration / unknown channel / missing config
# ---------------------------------------------------------------------------

def test_notify_slack_without_integration_is_loud_failure(db, monkeypatch):
    """AC7: no connected Slack integration → ok=False, specific reason, no send."""
    org = _make_org(db)
    fake, calls = _recording_slack_sender()
    monkeypatch.setattr("src.tasks.alerts.send_slack_message_webhook", fake)

    exe = _build_run(db, org.id, {"channel": "slack", "message": "hi"})
    updated = _execute(db, exe)

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "no slack integration connected" == entry["error"]


def test_notify_unknown_channel_is_loud_failure(db, monkeypatch):
    """AC7: an unknown channel → ok=False, loud, nothing sent."""
    org = _make_org(db)
    fake, calls = _recording_slack_sender()
    monkeypatch.setattr("src.tasks.alerts.send_slack_message_webhook", fake)

    exe = _build_run(db, org.id, {"channel": "telegram", "message": "hi"})
    updated = _execute(db, exe)

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "unknown notify channel" in entry["error"]
    assert "telegram" in entry["error"]


def test_notify_missing_message_is_loud_failure(db, monkeypatch):
    """Config without a message → ok=False before any send."""
    org = _make_org(db)
    fake, calls = _recording_slack_sender()
    monkeypatch.setattr("src.tasks.alerts.send_slack_message_webhook", fake)

    exe = _build_run(db, org.id, {"channel": "slack"})
    updated = _execute(db, exe)

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "message" in entry["error"]


# ---------------------------------------------------------------------------
# AC8 — a failing notify never blocks sibling actions
# ---------------------------------------------------------------------------

def test_failing_notify_does_not_stop_sibling_actions(db, monkeypatch):
    """AC8: an unknown-channel notify (ok=False) is logged loudly; the next
    action still runs and succeeds."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "notify", "config": {"channel": "carrier-pigeon", "message": "hi"}},
        {"type": "tag", "config": {"tag": "at-risk"}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")
    updated = _execute(db, exe)

    assert len(updated.action_log) == 2
    assert updated.action_log[0]["ok"] is False
    assert "unknown notify channel" in updated.action_log[0]["error"]
    assert updated.action_log[1]["type"] == "tag"
    assert updated.action_log[1]["ok"] is True
    assert updated.status == "done"