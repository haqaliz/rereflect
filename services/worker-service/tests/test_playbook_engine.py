"""
Tests for playbook_engine.execute() — Phase 5.2 (M4.1).

Written RED-first (TDD). All ~14 tests must fail before implementation,
then pass after src/services/playbook_engine.py is complete.

Pattern mirrors test_probability_updater.py: in-memory SQLite, no real DB.
Action handlers are monkeypatched to isolate engine logic.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import JSON, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    CustomerHealth,
    Organization,
    User,
    ChurnPlaybook,
    ChurnPlaybookExecution,
)

# ---------------------------------------------------------------------------
# In-memory DB wiring
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
# Helper builders
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
            {"type": "assign", "config": {"assign_to": "round_robin"}},
            {"type": "send_notification", "config": {"recipients": "admins"}},
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
    created_at: datetime = None,
) -> ChurnPlaybookExecution:
    exe = ChurnPlaybookExecution(
        playbook_id=playbook_id,
        organization_id=org_id,
        customer_email=customer_email,
        triggered_by="manual",
        status=status,
        action_log=[],
        created_at=created_at or datetime.utcnow(),
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


def _make_user(db, org_id: int, email: str = "owner@example.com") -> User:
    user = User(
        email=email,
        organization_id=org_id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Import module under test (after models are importable)
# ---------------------------------------------------------------------------

from src.services import playbook_engine  # noqa: E402


# ---------------------------------------------------------------------------
# Worker model mirror parity (playbook-send-email-step)
# ---------------------------------------------------------------------------


def test_worker_customer_health_mirrors_cs_owner_user_id_column():
    """Mirror parity: backend CustomerHealth.cs_owner_user_id (Integer FK) has a
    plain nullable Integer mirror column for the send_email cs_assignee recipient."""
    cols = {c.name: c for c in CustomerHealth.__table__.columns}
    assert "cs_owner_user_id" in cols
    col = cols["cs_owner_user_id"]
    assert col.nullable is True
    assert isinstance(col.type, Integer)


def test_worker_customer_health_mirrors_tags_column(db):
    """Mirror parity: backend CustomerHealth.tags (JSON, nullable, default=list)
    has a JSON mirror column whose default is the `list` callable (never a shared
    [] literal) and which round-trips a list through the DB."""
    cols = {c.name: c for c in CustomerHealth.__table__.columns}
    assert "tags" in cols
    col = cols["tags"]
    assert col.nullable is True
    assert isinstance(col.type, JSON)
    # SQLAlchemy 2.x wraps callable defaults in a lambda (schema.py
    # util.wrap_callable), so assert callability — NOT `arg is list` — to
    # guard the mutable-default trap (a shared [] literal is not callable).
    assert callable(col.default.arg)

    health = CustomerHealth(
        organization_id=1,
        customer_email="tags@example.com",
        tags=["beta", "alpha"],
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    assert health.tags == ["beta", "alpha"]


def test_worker_organization_mirrors_product_name_display_column():
    """Mirror parity: backend Organization.product_name_display (String(200)) has a
    nullable String(200) mirror column for send_email template rendering."""
    cols = {c.name: c for c in Organization.__table__.columns}
    assert "product_name_display" in cols
    col = cols["product_name_display"]
    assert col.nullable is True
    assert isinstance(col.type, String)
    assert col.type.length == 200


def test_worker_playbook_task_mirror_matches_backend_columns():
    """Mirror parity: the worker PlaybookTask mirror columns must exactly
    match the backend-api model (playbook-action-types aspect). A drift here
    is silent: the worker would read/write a column under a different name,
    or miss one entirely, and fail at runtime rather than in a test.

    Same sys.path/sys.modules swap technique as
    test_zendesk_adapter.py::TestModelsAndMigration.
    """
    import os
    import sys

    from src.models import PlaybookTask as WorkerModel

    worker_cols = {c.name for c in WorkerModel.__table__.columns}

    worktree = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    backend_src = os.path.join(worktree, "services", "backend-api")

    saved_mods = {
        k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")
    }
    for k in saved_mods:
        del sys.modules[k]

    sys.path.insert(0, backend_src)
    try:
        from src.models.playbook_task import PlaybookTask as BackendModel

        backend_cols = {c.name for c in BackendModel.__table__.columns}
    finally:
        sys.path.remove(backend_src)
        for k in list(sys.modules.keys()):
            if k == "src" or k.startswith("src."):
                del sys.modules[k]
        sys.modules.update(saved_mods)

    assert worker_cols == backend_cols, (
        f"Column mismatch!\n"
        f"  Worker only:  {worker_cols - backend_cols}\n"
        f"  Backend only: {backend_cols - worker_cols}"
    )


# ---------------------------------------------------------------------------
# send_email step — recipient resolution (playbook-send-email-step)
# ---------------------------------------------------------------------------

def _fake_sender(result_dict):
    """Build a fake send_outreach_email that records its call args and returns
    `result_dict` (spec table {ok, status, reason})."""
    calls = []

    def fake_send(db, org_id, customer_email, subject, body, *, product_name, template_key=None):
        calls.append({
            "org_id": org_id,
            "customer_email": customer_email,
            "subject": subject,
            "body": body,
            "product_name": product_name,
            "template_key": template_key,
        })
        return result_dict

    return fake_send, calls


def _run_send_email_playbook(db, config, *, health_kwargs=None, product_name_display=None):
    org = _make_org(db)
    if product_name_display is not None:
        org.product_name_display = product_name_display
        db.commit()
    pb = _make_playbook(
        db, org.id,
        action_sequence=[{"type": "send_email", "config": config}],
    )
    health = _make_health(db, org.id)
    for k, v in (health_kwargs or {}).items():
        setattr(health, k, v)
    db.commit()
    exe = _make_execution(db, pb.id, org.id, status="queued")
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    return db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first(), org, health


def test_send_email_recipient_customer_uses_execution_customer_email(db, monkeypatch):
    """AC1: recipient 'customer' → sender receives the execution's customer_email."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(
        db, {"template": "re_engagement", "recipient": "customer"},
    )

    assert len(calls) == 1
    assert calls[0]["customer_email"] == "customer@example.com"
    assert calls[0]["template_key"] == "re_engagement"
    assert updated.status == "done"
    entry = updated.action_log[0]
    assert entry == {
        "type": "send_email",
        "ok": True,
        "result": {
            "status": "sent",
            "reason": "",
            "to": "customer@example.com",
            "template": "re_engagement",
        },
        "error": None,
    }


def test_send_email_recipient_cs_assignee_resolves_owner_email(db, monkeypatch):
    """AC2: recipient 'cs_assignee' → health.cs_owner_user_id → users.email."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    org = _make_org(db)
    user = _make_user(db, org.id, email="cs-owner@example.com")
    pb = _make_playbook(
        db, org.id,
        action_sequence=[{
            "type": "send_email",
            "config": {"template": "weekly_digest_entry", "recipient": "cs_assignee"},
        }],
    )
    health = _make_health(db, org.id)
    health.cs_owner_user_id = user.id
    db.commit()
    exe = _make_execution(db, pb.id, org.id, status="queued")
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()

    assert len(calls) == 1
    assert calls[0]["customer_email"] == "cs-owner@example.com"
    assert updated.status == "done"
    assert updated.action_log[0]["ok"] is True
    assert updated.action_log[0]["result"]["to"] == "cs-owner@example.com"


def test_send_email_cs_assignee_without_owner_is_loud_failure(db, monkeypatch):
    """AC2: no cs_owner_user_id → ok=False, error mentions owner, sender NOT called."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(
        db, {"template": "weekly_digest_entry", "recipient": "cs_assignee"},
    )

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["result"] is None
    assert entry["error"] == (
        "cs_assignee recipient requested but customer has no assigned CS owner"
    )
    assert updated.status == "failed"


def test_send_email_cs_assignee_missing_user_row_is_loud_failure(db, monkeypatch):
    """Owner id set but no users row → ok=False (loud), sender NOT called."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(
        db, {"template": "weekly_digest_entry", "recipient": "cs_assignee"},
        health_kwargs={"cs_owner_user_id": 999999},
    )

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["result"] is None
    assert entry["error"] == "cs_assignee user 999999 not found"
    assert updated.status == "failed"


# ---------------------------------------------------------------------------
# send_email step — rendering via the real registry mirror
# ---------------------------------------------------------------------------

def test_send_email_renders_template_with_customer_and_product_names(db, monkeypatch):
    """AC3: real registry mirror substitutes customer name + product_name_display."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    _run_send_email_playbook(
        db, {"template": "weekly_digest_entry", "recipient": "customer"},
        health_kwargs={"customer_name": "Jane Doe"},
        product_name_display="Acme Analytics",
    )

    assert len(calls) == 1
    assert "Jane Doe" in calls[0]["body"]
    assert "Acme Analytics" in calls[0]["body"]
    assert "Acme Analytics" in calls[0]["subject"]
    assert calls[0]["product_name"] == "Acme Analytics"


def test_send_email_renders_fallbacks_name_and_product(db, monkeypatch):
    """AC3: customer_name null → email local-part; product_name_display unset → Rereflect."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    _run_send_email_playbook(
        db, {"template": "re_engagement", "recipient": "customer"},
    )

    assert len(calls) == 1
    assert "Hi customer," in calls[0]["body"]
    assert "used Rereflect" in calls[0]["body"]
    assert calls[0]["product_name"] == "Rereflect"


def test_send_email_unknown_template_key_is_loud_failure(db, monkeypatch):
    """AC4: unknown template key → ok=False, error contains the key, sender NOT called."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(
        db, {"template": "no_such_template", "recipient": "customer"},
    )

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["result"] is None
    assert entry["error"] == "unknown outreach template: 'no_such_template'"


# ---------------------------------------------------------------------------
# send_email step — config validation
# ---------------------------------------------------------------------------

def test_send_email_missing_template_is_loud_failure(db, monkeypatch):
    """AC5: missing 'template' → ok=False, sender NOT called."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(db, {"recipient": "customer"})

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == "send_email step missing 'template' in config"


def test_send_email_missing_recipient_is_loud_failure(db, monkeypatch):
    """AC5: missing 'recipient' → ok=False, sender NOT called."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(db, {"template": "re_engagement"})

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == "send_email step missing 'recipient' in config"


def test_send_email_unknown_recipient_is_loud_failure(db, monkeypatch):
    """AC5: unknown recipient value → ok=False, sender NOT called."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(
        db, {"template": "re_engagement", "recipient": "boss"},
    )

    assert calls == []
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == "unsupported send_email recipient: 'boss'"


# ---------------------------------------------------------------------------
# Seeded templates pinned green (playbook-send-email-step, PRD goal #1)
# ---------------------------------------------------------------------------

AT_RISK_OUTREACH_SEED = [
    {"type": "send_email", "config": {"template": "weekly_digest_entry", "recipient": "cs_assignee"}},
    {"type": "tag", "config": {"tag": "at-risk"}},
    {"type": "send_notification", "config": {"recipients": "assignee", "channels": ["dashboard"], "message": "Customer flagged as at-risk."}},
]

SILENT_CHURN_WATCH_SEED = [
    {"type": "send_email", "config": {"template": "re_engagement", "recipient": "customer"}},
    {"type": "create_task", "config": {"description": "Follow-up: confirm engagement or mark silent churn", "due_in_days": 14, "priority": "medium"}},
]


# ---------------------------------------------------------------------------
# send_email step — sender result mapping (spec table)
# ---------------------------------------------------------------------------

def test_seed_at_risk_outreach_send_email_step_runs_green(db, monkeypatch):
    """AC8: 'At-Risk Outreach' seed runs through the real engine (sender mocked);
    its send_email step (weekly_digest_entry → cs_assignee) logs ok=True and the
    run finishes done with the seed's full step count."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    org = _make_org(db)
    user = _make_user(db, org.id, email="cs-owner@example.com")
    pb = _make_playbook(db, org.id, action_sequence=AT_RISK_OUTREACH_SEED)
    health = _make_health(db, org.id)
    health.cs_owner_user_id = user.id
    db.commit()
    exe = _make_execution(db, pb.id, org.id, status="queued")
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()

    assert len(calls) == 1
    assert calls[0]["customer_email"] == "cs-owner@example.com"
    assert calls[0]["template_key"] == "weekly_digest_entry"
    assert len(updated.action_log) == 3
    email_entry = updated.action_log[0]
    assert email_entry["type"] == "send_email"
    assert email_entry["ok"] is True
    assert email_entry["result"]["template"] == "weekly_digest_entry"
    assert email_entry["result"]["status"] == "sent"
    assert updated.status == "done"


def test_seed_silent_churn_watch_send_email_step_runs_green(db, monkeypatch):
    """AC8: 'Silent-Churn Watch' seed runs through the real engine (sender mocked);
    its send_email step (re_engagement → customer) logs ok=True and the run
    finishes done with the seed's full step count."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=SILENT_CHURN_WATCH_SEED)
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()

    assert len(calls) == 1
    assert calls[0]["customer_email"] == "customer@example.com"
    assert calls[0]["template_key"] == "re_engagement"
    assert len(updated.action_log) == 2
    email_entry = updated.action_log[0]
    assert email_entry["type"] == "send_email"
    assert email_entry["ok"] is True
    assert email_entry["result"]["template"] == "re_engagement"
    assert email_entry["result"]["status"] == "sent"
    assert updated.status == "done"

@pytest.mark.parametrize(
    "sender_result, expected_ok",
    [
        ({"ok": True, "status": "sent", "reason": ""}, True),
        ({"ok": False, "status": "skipped", "reason": "opted out"}, False),
        ({"ok": False, "status": "skipped", "reason": "in cooldown"}, False),
        ({"ok": False, "status": "failed", "reason": "email not configured"}, False),
    ],
)
def test_send_email_sender_result_mapping(
    db, monkeypatch, sender_result, expected_ok
):
    """AC6: spec-table mapping — status/reason passthrough into the action_log entry."""
    fake_send, calls = _fake_sender(sender_result)
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(
        db, {"template": "re_engagement", "recipient": "customer"},
    )

    assert len(calls) == 1
    entry = updated.action_log[0]
    assert entry["ok"] is expected_ok
    assert entry["error"] is None
    assert entry["result"] == {
        "status": sender_result["status"],
        "reason": sender_result["reason"],
        "to": "customer@example.com",
        "template": "re_engagement",
    }


# ---------------------------------------------------------------------------
# send_email step — run status consistency
# ---------------------------------------------------------------------------

def test_send_email_only_playbook_sent_is_done(db, monkeypatch):
    """AC7: send_email-only playbook with a sent email → execution done."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(
        db, {"template": "re_engagement", "recipient": "customer"},
    )

    assert updated.status == "done"
    assert updated.action_log[0]["ok"] is True


def test_send_email_only_playbook_skipped_is_failed(db, monkeypatch):
    """AC7: send_email-only playbook with a skipped email → execution failed (no false success)."""
    fake_send, calls = _fake_sender(
        {"ok": False, "status": "skipped", "reason": "opted out"}
    )
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    updated, _, _ = _run_send_email_playbook(
        db, {"template": "re_engagement", "recipient": "customer"},
    )

    assert updated.status == "failed"
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["result"]["status"] == "skipped"
    assert entry["result"]["reason"] == "opted out"


def test_send_email_seed_shape_silent_churn_watch_is_done_with_loud_entry(db, monkeypatch):
    """AC7: 'Silent-Churn Watch' seed shape (send_email + create_task) with the
    sender mocked to sent → done; the send_email entry is recorded loudly."""
    fake_send, calls = _fake_sender({"ok": True, "status": "sent", "reason": ""})
    monkeypatch.setattr(
        "src.services.outreach_sender.send_outreach_email", fake_send
    )

    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "send_email", "config": {"template": "re_engagement", "recipient": "customer"}},
        {"type": "create_task", "config": {"description": "Follow-up", "due_in_days": 14, "priority": "medium"}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()

    assert updated.status == "done"
    assert len(updated.action_log) == 2
    email_entry = updated.action_log[0]
    assert email_entry["type"] == "send_email"
    assert email_entry["ok"] is True
    assert email_entry["result"]["status"] == "sent"
    assert email_entry["result"]["template"] == "re_engagement"
    assert "ok" in updated.action_log[1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_execute_loads_execution_by_id_and_sets_running(db):
    """Engine loads execution by id and transitions status from queued → running."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[{"type": "assign", "config": {}}])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    playbook_engine.execute(exe.id, db)

    # Re-query to see persisted state
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status in ("done", "failed")  # ran to completion
    assert updated.started_at is not None


def test_execute_returns_early_when_execution_already_done(db):
    """If status is already 'done', engine returns immediately (idempotent)."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="done")
    fixed_completed_at = datetime(2026, 1, 1, 10, 0, 0)
    exe.completed_at = fixed_completed_at
    db.commit()

    result = playbook_engine.execute(exe.id, db)

    assert result is not None
    assert result.get("skipped") is True
    db.expire_all()
    unchanged = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert unchanged.completed_at == fixed_completed_at


def test_execute_returns_early_when_execution_already_running(db):
    """If status is 'running', engine returns immediately (prevents double-execution)."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="running")

    result = playbook_engine.execute(exe.id, db)

    assert result is not None
    assert result.get("skipped") is True


def test_execute_fails_gracefully_when_playbook_deleted(db):
    """Execution with missing playbook gets status='failed', error_message set."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    # Detach playbook relationship then delete it
    db.delete(pb)
    db.commit()

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"
    assert "deleted" in (updated.error_message or "").lower()


def test_execute_fails_gracefully_when_customer_health_missing(db):
    """No CustomerHealth row → status='failed', error_message mentions customer."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    # Intentionally no _make_health call
    exe = _make_execution(db, pb.id, org.id, customer_email="ghost@example.com", status="queued")

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"
    assert updated.error_message is not None


def test_execute_runs_all_actions_in_sequence(db, monkeypatch):
    """Each action in action_sequence is dispatched to its handler."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    dispatched = []

    def fake_handler(action_type, action_config, customer_email, health, db, execution_id=None):
        dispatched.append(action_type)
        return {"ok": True, "result": {}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    assert dispatched == ["assign", "send_notification"]


def test_execute_continues_after_action_failure(db, monkeypatch):
    """If action 1 fails, action 2 still executes (no short-circuit)."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    dispatched = []

    def fake_handler(action_type, action_config, customer_email, health, db, execution_id=None):
        dispatched.append(action_type)
        if action_type == "assign":
            raise RuntimeError("assign exploded")
        return {"ok": True, "result": {}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    assert "assign" in dispatched
    assert "send_notification" in dispatched


def test_execute_action_log_records_each_outcome(db, monkeypatch):
    """action_log is persisted as a list with one entry per action."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    def fake_handler(action_type, action_config, customer_email, health, db, execution_id=None):
        return {"ok": True, "result": {"done": True}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert isinstance(updated.action_log, list)
    assert len(updated.action_log) == 2
    for entry in updated.action_log:
        assert "type" in entry
        assert "ok" in entry


def test_execute_marks_done_when_any_action_succeeds(db, monkeypatch):
    """status='done' when at least one action returns ok=True."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    call_count = [0]

    def fake_handler(action_type, action_config, customer_email, health, db, execution_id=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("first action fails")
        return {"ok": True, "result": {}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "done"


def test_execute_marks_failed_when_all_actions_fail(db, monkeypatch):
    """status='failed' when every action raises or returns ok=False."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    def fake_handler(action_type, action_config, customer_email, health, db, execution_id=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"


def test_execute_unsupported_action_type_logged_not_crashed(db, monkeypatch):
    """Unsupported action type is logged in action_log but does not raise."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "send_spaceship", "config": {}},  # unsupported
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    # Do NOT monkeypatch _dispatch_action — let real one handle unknown type
    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"  # only action failed
    assert len(updated.action_log) == 1
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "unsupported" in (entry.get("error") or "").lower()


def test_execute_rate_limited_when_same_playbook_recently_ran_for_customer(db):
    """
    If a done execution exists for same (playbook_id, customer_email) within
    last 60 minutes, new execution is cancelled with error_message='rate-limited'.
    """
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[{"type": "assign", "config": {}}])
    _make_health(db, org.id)

    # Seed a done execution 30 minutes ago
    recent_done = _make_execution(
        db, pb.id, org.id,
        customer_email="customer@example.com",
        status="done",
        created_at=datetime.utcnow() - timedelta(minutes=30),
    )

    # New queued execution for the same customer
    new_exe = _make_execution(db, pb.id, org.id, status="queued")

    playbook_engine.execute(new_exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=new_exe.id).first()
    assert updated.status == "cancelled"
    assert "rate" in (updated.error_message or "").lower()


def test_execute_allows_run_after_60_minute_window(db):
    """
    A done execution older than 60 minutes does NOT rate-limit the new one.
    """
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[{"type": "assign", "config": {}}])
    _make_health(db, org.id)

    # Seed a done execution 90 minutes ago (outside window)
    _make_execution(
        db, pb.id, org.id,
        customer_email="customer@example.com",
        status="done",
        created_at=datetime.utcnow() - timedelta(minutes=90),
    )

    new_exe = _make_execution(db, pb.id, org.id, status="queued")

    playbook_engine.execute(new_exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=new_exe.id).first()
    assert updated.status != "cancelled"


def test_execute_persists_started_at_and_completed_at(db, monkeypatch):
    """started_at and completed_at are both set after a successful run."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[{"type": "assign", "config": {}}])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    def fake_handler(action_type, action_config, customer_email, health, db, execution_id=None):
        return {"ok": True, "result": {}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    before = datetime.utcnow()
    playbook_engine.execute(exe.id, db)
    after = datetime.utcnow()

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.started_at is not None
    assert updated.completed_at is not None
    assert before <= updated.started_at <= after
    assert updated.started_at <= updated.completed_at
