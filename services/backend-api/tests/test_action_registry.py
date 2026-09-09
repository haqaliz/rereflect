"""
TDD tests — action registry (`src/services/copilot/action_registry.py`).

The registry is the ONLY dispatch path for copilot-suggested actions (PRD M1):
it maps a stable `action` id to an entry declaring `min_role`, a params
validator, and the executor callable. Unknown ids are rejected before anything
runs; `min_role` is enforced by the registry at execute time, independent of
any route's own dependency (PRD M5).

See docs/planning/copilot-suggested-actions/action-registry/{plan,spec}.
"""
import pytest

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.schemas.cohort import BulkActionSummary
from src.services.copilot.action_registry import (
    ACTION_REGISTRY,
    ActionEntry,
    COPILOT_ACTION_AUDIT_ACTION,
    InsufficientRoleError,
    UnknownActionError,
    get_entry,
    require_role,
    role_level,
)


class _User:
    """Minimal stand-in for a route User — only `.role` is read by the registry."""

    def __init__(self, role: str):
        self.role = role


class TestRegistryShape:
    def test_registry_contains_exactly_tag_customers(self):
        assert set(ACTION_REGISTRY) == {"tag_customers"}

    def test_registry_contains_only_action_entries(self):
        for entry in ACTION_REGISTRY.values():
            assert isinstance(entry, ActionEntry)

    def test_tag_customers_entry_declares_admin_min_role(self):
        assert ACTION_REGISTRY["tag_customers"].min_role == "admin"

    def test_tag_customers_entry_has_callable_executor_and_params_validator(self):
        entry = ACTION_REGISTRY["tag_customers"]
        assert callable(entry.executor)
        assert callable(entry.params_validator)

    def test_audit_action_constant(self):
        assert COPILOT_ACTION_AUDIT_ACTION == "copilot_action_executed"

    def test_role_level_map(self):
        assert role_level == {"member": 1, "admin": 2, "owner": 3}


class TestGetEntry:
    def test_known_action_returns_entry(self):
        assert get_entry("tag_customers").action_id == "tag_customers"

    def test_unknown_action_raises_unknown_action_error(self):
        with pytest.raises(UnknownActionError):
            get_entry("no_such_action")

    def test_unknown_action_error_carries_the_action_id(self):
        with pytest.raises(UnknownActionError) as exc:
            get_entry("mystery_action")
        assert str(exc.value) == "mystery_action"


class TestRequireRole:
    def test_member_denied_for_admin_action(self):
        entry = get_entry("tag_customers")
        with pytest.raises(InsufficientRoleError):
            require_role(entry, _User(role="member"))

    def test_admin_allowed_for_admin_action(self):
        entry = get_entry("tag_customers")
        assert require_role(entry, _User(role="admin")) is None

    def test_owner_allowed_for_admin_action(self):
        entry = get_entry("tag_customers")
        assert require_role(entry, _User(role="owner")) is None


class TestRegistryDriftGuard:
    def test_every_entry_min_role_is_at_least_as_strict_as_its_executor_route(self):
        """Every entry's `min_role` must be >= the role level its executor
        route's own dependency enforces (spec risk table / PRD M5).

        Slice-1 executor routes and their dependency levels:
          - tag_customers -> POST /api/v1/customers/bulk/tags
            -> require_admin_or_owner -> level >= 2
        When a new action is added whose executor has a route-level gate,
        extend this map — the guard is what stops the registry drifting weaker.
        """
        executor_route_level = {"tag_customers": 2}
        for action_id, entry in ACTION_REGISTRY.items():
            assert (
                role_level[entry.min_role] >= executor_route_level[action_id]
            ), (
                f"registry min_role='{entry.min_role}' for '{action_id}' is weaker "
                f"than its executor route's own dependency "
                f"(level {executor_route_level[action_id]})"
            )


class TestTagCustomersParamsValidator:
    def test_valid_tag_returns_stripped_tag(self):
        entry = get_entry("tag_customers")
        assert entry.params_validator({"tag": "  vip  "}) == "vip"

    def test_missing_tag_raises_value_error(self):
        entry = get_entry("tag_customers")
        with pytest.raises(ValueError):
            entry.params_validator({})

    def test_empty_or_whitespace_tag_raises_value_error(self):
        entry = get_entry("tag_customers")
        with pytest.raises(ValueError):
            entry.params_validator({"tag": "   "})

    def test_tag_over_50_chars_raises_value_error(self):
        entry = get_entry("tag_customers")
        with pytest.raises(ValueError):
            entry.params_validator({"tag": "x" * 51})


def make_ch(db, org: Organization, email: str, **kwargs) -> CustomerHealth:
    from datetime import datetime

    defaults = dict(
        health_score=60,
        risk_level="moderate",
        feedback_count=5,
        confidence_level="medium",
        last_feedback_at=datetime.utcnow(),
        is_archived=False,
        churn_risk_component=50,
        sentiment_component=60,
        resolution_component=70,
        frequency_component=55,
    )
    defaults.update(kwargs)
    record = CustomerHealth(organization_id=org.id, customer_email=email, **defaults)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


class TestTagCustomersExecutor:
    def test_executor_resolves_frozen_emails_and_applies_tag(self, db):
        org = Organization(name="Registry Co", plan="business")
        db.add(org)
        db.commit()
        db.refresh(org)
        make_ch(db, org, "ada@example.com", tags=["existing"])

        result = get_entry("tag_customers").executor(
            db, org, emails=["ada@example.com"], tag="vip"
        )

        assert result == BulkActionSummary(matched=1, updated=1, skipped=0, errors=[])
        row = db.query(CustomerHealth).filter_by(customer_email="ada@example.com").first()
        assert row.tags == ["existing", "vip"]

    def test_executor_absorbs_foreign_and_unknown_emails_as_skipped(self, db):
        org = Organization(name="Registry Co", plan="business")
        db.add(org)
        db.commit()
        db.refresh(org)
        make_ch(db, org, "ada@example.com")

        result = get_entry("tag_customers").executor(
            db,
            org,
            emails=["ada@example.com", "foreign@other.com", "nobody@example.com"],
            tag="vip",
        )

        assert result == BulkActionSummary(matched=1, updated=1, skipped=2, errors=[])
        row = db.query(CustomerHealth).filter_by(customer_email="ada@example.com").first()
        assert row.tags == ["vip"]

    def test_executor_reports_over_cap_rows_in_errors(self, db):
        org = Organization(name="Registry Co", plan="business")
        db.add(org)
        db.commit()
        db.refresh(org)
        full = make_ch(db, org, "full@example.com", tags=[f"tag{i}" for i in range(20)])
        room = make_ch(db, org, "room@example.com", tags=[])

        result = get_entry("tag_customers").executor(
            db, org, emails=["full@example.com", "room@example.com"], tag="vip"
        )

        assert result.matched == 2
        assert result.updated == 1
        assert len(result.errors) == 1
        assert "full@example.com" in result.errors[0]
        assert len(full.tags) == 20  # unchanged
        assert room.tags == ["vip"]
