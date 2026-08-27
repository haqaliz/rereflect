"""
Tests for the `trigger_automation` playbook action —
playbook_engine._handle_trigger_automation (trigger-automation aspect, M4).

TDD: written RED-first — every test fails with
`unsupported action type: 'trigger_automation'` until the handler lands.

Firing reuses the existing single-rule entry `_evaluate_rule` in
automation_churn_trigger.py (never modified here); threshold + cooldown
semantics are delegated to it. Redis cooldown is exercised via a recording
`_get_redis` fake; `run_playbook.delay` is patched — no broker needed.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    CustomerHealth,
    Organization,
    ChurnPlaybook,
    ChurnPlaybookExecution,
)
from src.models.automation_execution import AutomationExecution
from src.models.automation_rule import AutomationRule

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
            {"type": "trigger_automation", "config": {"automation_name": "Save"}},
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


def _make_rule(
    db,
    org_id: int = 1,
    name: str = "High churn risk -> playbook",
    mode: str = "active",
    trigger_type: str = "churn_probability_threshold",
    threshold: float = 0.6,
    cooldown_hours: int = 24,
    playbook_id: int = None,
    created_at: datetime = None,
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name=name,
        trigger_type=trigger_type,
        trigger_config={"threshold": threshold},
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook_id}}],
        cooldown_hours=cooldown_hours,
        mode=mode,
    )
    if created_at is not None:
        rule.created_at = created_at
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


class RecordingRedis:
    """Recording fake for _get_redis: reports a fixed `exists` answer and
    records every setex call (cooldown writes)."""

    def __init__(self, exists_result: bool = False):
        self.exists_result = exists_result
        self.setex_calls = []

    def exists(self, key):
        return self.exists_result

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))


def _run_trigger_playbook(
    db, org_id, automation_name, *, probability=None, email="customer@example.com",
    action_sequence=None,
):
    pb = _make_playbook(db, org_id, action_sequence=action_sequence or [
        {"type": "trigger_automation", "config": {"automation_name": automation_name}},
    ])
    health = _make_health(db, org_id, email=email)
    if probability is not None:
        health.churn_probability = probability
    db.commit()
    exe = _make_execution(db, pb.id, org_id, customer_email=email, status="queued")

    from src.services import playbook_engine
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    return updated


def _patch_seams(monkeypatch, redis=None):
    """Patch the churn-trigger seams: Redis fake + run_playbook.delay."""
    if redis is None:
        redis = RecordingRedis()
    monkeypatch.setattr(
        "src.services.automation_churn_trigger._get_redis", lambda: redis
    )
    fake_task = MagicMock()
    monkeypatch.setattr("src.services.automation_churn_trigger.run_playbook", fake_task)
    return redis, fake_task


# ---------------------------------------------------------------------------
# AC1 — active rule, threshold breached → fired
# ---------------------------------------------------------------------------

def test_trigger_automation_fires_breached_active_rule(db, monkeypatch):
    """AC1: probability 0.9 vs threshold 0.6 → ok=True fired=True; the
    AutomationExecution row exists and the shared cooldown key was set."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, threshold=0.6, playbook_id=pb.id)
    redis, fake_task = _patch_seams(monkeypatch, redis=RecordingRedis())

    updated = _run_trigger_playbook(db, org.id, rule.name, probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"] == {
        "fired": True,
        "rule_id": rule.id,
        "automation_name": rule.name,
    }
    assert updated.status == "done"

    execution = db.query(AutomationExecution).filter_by(
        rule_id=rule.id, customer_email="customer@example.com"
    ).first()
    assert execution is not None
    assert execution.status == "success"

    cooldown_key = f"automation_cooldown:{rule.id}:customer@example.com"
    assert any(key == cooldown_key for key, _, _ in redis.setex_calls)
    assert fake_task.delay.called


# ---------------------------------------------------------------------------
# AC2 — below threshold → fired False (delegated)
# ---------------------------------------------------------------------------

def test_trigger_automation_below_threshold_not_fired(db, monkeypatch):
    """AC2: probability 0.5 vs threshold 0.6 → ok=True, fired=False with the
    rule's own threshold reason; no AutomationExecution row."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, threshold=0.6, playbook_id=pb.id)
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, rule.name, probability=0.5)

    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"]["fired"] is False
    assert "threshold" in entry["result"]["reason"].lower()
    assert (
        db.query(AutomationExecution)
        .filter_by(rule_id=rule.id, customer_email="customer@example.com")
        .count()
        == 0
    )
    assert updated.status == "done"


# ---------------------------------------------------------------------------
# AC3 — cooldown pre-set → skip
# ---------------------------------------------------------------------------

def test_trigger_automation_in_cooldown_not_fired(db, monkeypatch):
    """AC3: rule already in cooldown for the customer → ok=True, fired=False,
    reason mentions cooldown; no AutomationExecution row."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, threshold=0.6, playbook_id=pb.id)
    _patch_seams(monkeypatch, redis=RecordingRedis(exists_result=True))

    updated = _run_trigger_playbook(db, org.id, rule.name, probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"]["fired"] is False
    assert "cooldown" in entry["result"]["reason"].lower()
    assert (
        db.query(AutomationExecution)
        .filter_by(rule_id=rule.id, customer_email="customer@example.com")
        .count()
        == 0
    )


# ---------------------------------------------------------------------------
# AC4 — each loud branch, exact reason strings
# ---------------------------------------------------------------------------

def test_trigger_automation_unknown_rule_name_is_loud(db, monkeypatch):
    """AC4: no rule with that name → ok=False, 'no rule named '<name>''."""
    org = _make_org(db)
    _make_rule(db, org_id=org.id, name="Some other rule")
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, "No such rule", probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == "no rule named 'No such rule'"
    assert updated.status == "failed"


def test_trigger_automation_missing_automation_name_is_loud(db, monkeypatch):
    """AC4: missing/empty automation_name → ok=False mentioning the field."""
    org = _make_org(db)
    _make_rule(db, org_id=org.id)
    _patch_seams(monkeypatch)

    for i, name in enumerate(("", "   ")):
        updated = _run_trigger_playbook(
            db, org.id, name, probability=0.9, email=f"customer{i}@example.com",
        )
        entry = updated.action_log[0]
        assert entry["ok"] is False
        assert "automation_name" in entry["error"]


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_trigger_automation_non_active_mode_is_loud(db, monkeypatch, mode):
    """AC4: mode=off / mode=shadow → ok=False with the exact mode reason."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, mode=mode, playbook_id=pb.id)
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, rule.name, probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == f"rule '{rule.name}' found but mode={mode} — not fired"


def test_trigger_automation_zero_cooldown_is_refused(db, monkeypatch):
    """AC4: cooldown_hours=0 → ok=False, exact 'cooldown_hours < 1' reason."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, cooldown_hours=0, playbook_id=pb.id)
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, rule.name, probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == f"rule '{rule.name}' has cooldown_hours < 1 — refused"


def test_trigger_automation_missing_probability_is_loud(db, monkeypatch):
    """AC4: health.churn_probability None → ok=False with the exact reason."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, playbook_id=pb.id)
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, rule.name)  # probability None

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == "no churn probability available for customer"


def test_trigger_automation_other_trigger_type_is_loud(db, monkeypatch):
    """AC4: a non-churn trigger type → ok=False with its native-evaluator
    seam reason."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, trigger_type="sentiment_pattern", playbook_id=pb.id)
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, rule.name, probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == (
        "trigger type 'sentiment_pattern' fires only from its native evaluator"
    )


# ---------------------------------------------------------------------------
# AC5 — usage_trend seam reason
# ---------------------------------------------------------------------------

def test_trigger_automation_usage_trend_is_loud_with_seam_reason(db, monkeypatch):
    """AC5: a usage_trend rule → ok=False with the daily-recompute seam reason."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, trigger_type="usage_trend", playbook_id=pb.id)
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, rule.name, probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == (
        "trigger type 'usage_trend' fires only from the daily recompute seam"
    )


# ---------------------------------------------------------------------------
# AC6 — full run with trigger_automation finalizes done, action_log intact
# ---------------------------------------------------------------------------

def test_trigger_automation_run_finalizes_done_with_intact_log(db, monkeypatch):
    """AC6: a run containing trigger_automation (which commits mid-run via
    _evaluate_rule) finalizes 'done' with the full action_log intact."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "trigger_automation", "config": {"automation_name": "At Risk Outreach"}},
        {"type": "tag", "config": {"tag": "at-risk"}},
    ])
    rule = _make_rule(db, org_id=org.id, name="At Risk Outreach", threshold=0.6, playbook_id=pb.id)
    _patch_seams(monkeypatch)
    health = _make_health(db, org.id)
    health.churn_probability = 0.9
    db.commit()
    exe = _make_execution(db, pb.id, org.id, status="queued")

    from src.services import playbook_engine
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()

    assert updated.status == "done"
    assert len(updated.action_log) == 2
    assert updated.action_log[0]["type"] == "trigger_automation"
    assert updated.action_log[0]["ok"] is True
    assert updated.action_log[0]["result"] == {
        "fired": True,
        "rule_id": rule.id,
        "automation_name": "At Risk Outreach",
    }
    assert updated.action_log[1]["type"] == "tag"
    assert updated.action_log[1]["ok"] is True


# ---------------------------------------------------------------------------
# AC7 — cross-org rule never resolves
# ---------------------------------------------------------------------------

def test_trigger_automation_cross_org_rule_never_resolves(db, monkeypatch):
    """AC7: a rule belonging to another org is never resolved — the lookup is
    org-scoped and reports 'no rule named'. """
    org = _make_org(db)
    other_org = _make_org(db)
    pb = _make_playbook(db, org.id)
    other_rule = _make_rule(db, org_id=other_org.id, name="Other org rule", playbook_id=pb.id)
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, other_rule.name, probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert entry["error"] == f"no rule named '{other_rule.name}'"


# ---------------------------------------------------------------------------
# Ordering tie-break + name trimming (plan edge cases)
# ---------------------------------------------------------------------------

def test_trigger_automation_first_rule_by_created_at_wins(db, monkeypatch):
    """Two rules with the same name → the earliest (created_at, id) is the
    one reported in the result's rule_id."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    first = _make_rule(
        db, org_id=org.id, name="Duplicate name", playbook_id=pb.id,
        created_at=datetime.utcnow() - timedelta(days=2),
    )
    _make_rule(
        db, org_id=org.id, name="Duplicate name", playbook_id=pb.id,
        created_at=datetime.utcnow() - timedelta(days=1),
    )
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, "Duplicate name", probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"]["rule_id"] == first.id


def test_trigger_automation_trims_whitespace_around_name(db, monkeypatch):
    """The configured name is trimmed before the lookup."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    rule = _make_rule(db, org_id=org.id, name="Save Customer", playbook_id=pb.id)
    _patch_seams(monkeypatch)

    updated = _run_trigger_playbook(db, org.id, "  Save Customer  ", probability=0.9)

    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"]["automation_name"] == "Save Customer"