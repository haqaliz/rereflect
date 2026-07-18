"""
Tests for churn-cooldown seeding on rule activation (M4.4 churn-triggered-
playbooks, Task 7) — strict TDD (RED first).

Feature context: the churn trigger is level-based, so flipping a rule to
`active` would fire it for EVERY customer already above threshold on their
next recompute — a "stampede." `seed_churn_cooldowns()` pre-seeds the
per-(rule,customer) Redis cooldown for every customer currently above the
rule's threshold when a `churn_probability_threshold` rule transitions INTO
`active`, so only NEW crossings fire.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.services import automation_engine
from src.services.automation_engine import AutomationEngine, seed_churn_cooldowns


# ---------------------------------------------------------------------------
# Fake Redis — in-memory, supports the subset of the API the engine uses
# (ping / exists / setex) and records every setex call for assertions.
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.setex_calls: list[tuple] = []

    def ping(self) -> bool:
        return True

    def exists(self, key: str) -> bool:
        return key in self.store

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value
        self.setex_calls.append((key, ttl, value))


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    """Patch automation_engine._get_redis() to return a fresh FakeRedis."""
    fake = FakeRedis()
    monkeypatch.setattr(automation_engine, "_get_redis", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_health(
    db: Session, org: Organization, email: str, churn_probability
) -> CustomerHealth:
    health = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=50,
        risk_level="at_risk",
        churn_risk_component=50,
        sentiment_component=50,
        resolution_component=50,
        frequency_component=50,
        feedback_count=5,
        churn_probability=churn_probability,
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


def _churn_rule(
    db: Session, org: Organization, threshold: float = 0.7, mode: str = "shadow"
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org.id,
        name="Churn Risk Alert",
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": threshold, "direction": "above"},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}}],
        cooldown_hours=24,
        mode=mode,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _health_score_rule(db: Session, org: Organization, mode: str = "shadow") -> AutomationRule:
    rule = AutomationRule(
        organization_id=org.id,
        name="Health Score Alert",
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 30, "direction": "below"},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}}],
        cooldown_hours=24,
        mode=mode,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# 1. seed_churn_cooldowns() unit tests
# ---------------------------------------------------------------------------

def test_seed_churn_cooldowns_seeds_only_above_threshold_customers(
    db: Session, test_organization: Organization, fake_redis: FakeRedis
):
    rule = _churn_rule(db, test_organization, threshold=0.7)
    _make_health(db, test_organization, "above1@test.com", 0.75)
    _make_health(db, test_organization, "above2@test.com", 0.90)
    _make_health(db, test_organization, "below@test.com", 0.50)

    count = seed_churn_cooldowns(db, rule)

    assert count == 2
    seeded_keys = {c[0] for c in fake_redis.setex_calls}
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:above1@test.com" in seeded_keys
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:above2@test.com" in seeded_keys
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:below@test.com" not in seeded_keys


def test_seed_churn_cooldowns_noop_for_non_churn_trigger(
    db: Session, test_organization: Organization, fake_redis: FakeRedis
):
    rule = _health_score_rule(db, test_organization)
    _make_health(db, test_organization, "above@test.com", 0.95)

    count = seed_churn_cooldowns(db, rule)

    assert count == 0
    assert fake_redis.setex_calls == []


def test_seed_churn_cooldowns_redis_unavailable_returns_zero(
    db: Session, test_organization: Organization, monkeypatch
):
    monkeypatch.setattr(automation_engine, "_get_redis", lambda: None)
    rule = _churn_rule(db, test_organization, threshold=0.7)
    _make_health(db, test_organization, "above@test.com", 0.95)

    count = seed_churn_cooldowns(db, rule)

    assert count == 0


def test_seed_churn_cooldowns_ignores_null_probability(
    db: Session, test_organization: Organization, fake_redis: FakeRedis
):
    rule = _churn_rule(db, test_organization, threshold=0.7)
    _make_health(db, test_organization, "nodata@test.com", None)

    count = seed_churn_cooldowns(db, rule)

    assert count == 0
    assert fake_redis.setex_calls == []


# ---------------------------------------------------------------------------
# 2. Seeded cooldown actually suppresses evaluate(); new crossings still fire
# ---------------------------------------------------------------------------

def test_seeded_customer_does_not_fire_but_new_crossing_does(
    db: Session, test_organization: Organization, fake_redis: FakeRedis
):
    rule = _churn_rule(db, test_organization, threshold=0.7, mode="active")
    _make_health(db, test_organization, "already-at-risk@test.com", 0.80)
    _make_health(db, test_organization, "will-cross-later@test.com", 0.50)

    seeded = seed_churn_cooldowns(db, rule)
    assert seeded == 1

    engine = AutomationEngine(db)

    # Already-at-risk customer: cooldown was pre-seeded -> must NOT fire.
    results = engine.evaluate(
        test_organization.id,
        "churn_probability_threshold",
        {"churn_probability": 0.80, "customer_email": "already-at-risk@test.com"},
    )
    assert results == []

    # A customer who crosses the threshold AFTER seeding (no cooldown key
    # was set for them) -> must fire normally.
    results = engine.evaluate(
        test_organization.id,
        "churn_probability_threshold",
        {"churn_probability": 0.75, "customer_email": "will-cross-later@test.com"},
    )
    assert len(results) == 1
    assert results[0]["rule_id"] == rule.id


# ---------------------------------------------------------------------------
# 3. Wiring — update_rule transition detection
# ---------------------------------------------------------------------------

def test_update_rule_shadow_to_active_seeds_cooldowns(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    rule = _churn_rule(db, test_organization, threshold=0.7, mode="shadow")
    _make_health(db, test_organization, "above1@test.com", 0.75)
    _make_health(db, test_organization, "above2@test.com", 0.90)
    _make_health(db, test_organization, "below@test.com", 0.50)

    response = client.put(
        f"/api/v1/automations/{rule.id}", json={"mode": "active"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "active"

    seeded_keys = {c[0] for c in fake_redis.setex_calls}
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:above1@test.com" in seeded_keys
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:above2@test.com" in seeded_keys
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:below@test.com" not in seeded_keys


def test_update_rule_off_to_active_seeds_cooldowns(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    rule = _churn_rule(db, test_organization, threshold=0.7, mode="off")
    _make_health(db, test_organization, "above@test.com", 0.99)

    response = client.put(
        f"/api/v1/automations/{rule.id}", json={"mode": "active"}, headers=auth_headers
    )
    assert response.status_code == 200

    seeded_keys = {c[0] for c in fake_redis.setex_calls}
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:above@test.com" in seeded_keys


def test_update_rule_active_to_active_does_not_reseed(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    rule = _churn_rule(db, test_organization, threshold=0.7, mode="active")
    _make_health(db, test_organization, "above@test.com", 0.99)

    # No transition happened yet (rule was created directly in mode="active"
    # via the ORM helper, bypassing create_rule's seeding path) — clear the
    # slate and assert a same-mode update performs no seeding.
    fake_redis.setex_calls.clear()

    response = client.put(
        f"/api/v1/automations/{rule.id}", json={"name": "Renamed"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "active"
    assert fake_redis.setex_calls == []


def test_update_rule_health_score_going_active_does_not_seed(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    rule = _health_score_rule(db, test_organization, mode="shadow")
    _make_health(db, test_organization, "above@test.com", 0.99)

    response = client.put(
        f"/api/v1/automations/{rule.id}", json={"mode": "active"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert fake_redis.setex_calls == []


def test_update_rule_redis_unavailable_still_succeeds(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr(automation_engine, "_get_redis", lambda: None)
    rule = _churn_rule(db, test_organization, threshold=0.7, mode="shadow")
    _make_health(db, test_organization, "above@test.com", 0.99)

    response = client.put(
        f"/api/v1/automations/{rule.id}", json={"mode": "active"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "active"


# ---------------------------------------------------------------------------
# 4. Wiring — create_rule seeds when created directly active
# ---------------------------------------------------------------------------

def _churn_trigger_payload(threshold: float = 0.7, mode: str = "active") -> dict:
    return {
        "name": "Churn Risk Alert",
        "trigger": {
            "type": "churn_probability_threshold",
            "config": {"threshold": threshold, "direction": "above"},
        },
        "actions": [
            {"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}},
        ],
        "cooldown_hours": 24,
        "mode": mode,
    }


def test_create_rule_directly_active_seeds_cooldowns(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    _make_health(db, test_organization, "above@test.com", 0.85)
    _make_health(db, test_organization, "below@test.com", 0.40)

    response = client.post(
        "/api/v1/automations", json=_churn_trigger_payload(mode="active"), headers=auth_headers
    )
    assert response.status_code == 201
    rule_id = response.json()["id"]

    seeded_keys = {c[0] for c in fake_redis.setex_calls}
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule_id}:above@test.com" in seeded_keys
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule_id}:below@test.com" not in seeded_keys


def test_create_rule_as_shadow_does_not_seed(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    _make_health(db, test_organization, "above@test.com", 0.85)

    response = client.post(
        "/api/v1/automations", json=_churn_trigger_payload(mode="shadow"), headers=auth_headers
    )
    assert response.status_code == 201
    assert fake_redis.setex_calls == []


# ---------------------------------------------------------------------------
# 5. Shadow executions must be visible via GET /{rule_id}/executions
# ---------------------------------------------------------------------------

def test_toggle_rule_off_to_active_seeds_cooldowns(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    rule = _churn_rule(db, test_organization, threshold=0.7, mode="off")
    _make_health(db, test_organization, "above1@test.com", 0.75)
    _make_health(db, test_organization, "above2@test.com", 0.90)
    _make_health(db, test_organization, "below@test.com", 0.50)

    response = client.patch(f"/api/v1/automations/{rule.id}/toggle", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["mode"] == "active"

    seeded_keys = {c[0] for c in fake_redis.setex_calls}
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:above1@test.com" in seeded_keys
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:above2@test.com" in seeded_keys
    assert f"{automation_engine.COOLDOWN_KEY_PREFIX}:{rule.id}:below@test.com" not in seeded_keys


def test_toggle_rule_health_score_going_active_does_not_seed(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    rule = _health_score_rule(db, test_organization, mode="off")
    _make_health(db, test_organization, "above@test.com", 0.99)

    response = client.patch(f"/api/v1/automations/{rule.id}/toggle", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["mode"] == "active"
    assert fake_redis.setex_calls == []


def test_shadow_executions_visible_via_executions_endpoint(
    client: TestClient, db: Session, test_organization: Organization, auth_headers: dict, fake_redis: FakeRedis
):
    rule = _churn_rule(db, test_organization, threshold=0.7, mode="shadow")

    engine = AutomationEngine(db)
    results = engine.evaluate(
        test_organization.id,
        "churn_probability_threshold",
        {"churn_probability": 0.9, "customer_email": "shadow-customer@test.com"},
    )
    # Shadow rules produce a summary too (status="shadow"), but no actions run.
    assert len(results) == 1
    assert results[0]["status"] == "shadow"

    response = client.get(f"/api/v1/automations/{rule.id}/executions", headers=auth_headers)
    assert response.status_code == 200
    executions = response.json()
    assert len(executions) == 1
    assert executions[0]["status"] == "shadow"
    assert executions[0]["customer_email"] == "shadow-customer@test.com"
