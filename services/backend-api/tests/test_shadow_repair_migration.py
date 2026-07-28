"""
TDD migration test for Phase 4 of the worker-trigger-mirror aspect
(automations-delivery-integrity): the repaired trigger types
(`feedback_category_match`, `sentiment_pattern`) are moved from
`mode='active'` to `mode='shadow'` on upgrade, so fixing the dead worker
import does not silently activate rules users configured months ago that
have never once run.

See docs/planning/automations-delivery-integrity/worker-trigger-mirror/plan_20260729.md
(Phase 4) and docs/planning/automations-delivery-integrity/prd.md (R3, Risk 1).

Strategy
--------
`automation_rules.mode` already exists (added by
u4v5w6x7y8z9_add_automation_rule_mode.py) — this migration only rewrites
data. So the test runs against the full ORM schema (via the shared `db`
fixture and the `AutomationRule` model) and applies the migration's
`upgrade()` / `downgrade()` through the Alembic Operations proxy bound to the
session's own connection, then asserts on `AutomationRule.mode` via fresh
queries.

The migration module is located by filename glob, never by grepping other
version files for `down_revision`/`revision` ids (that has caused a
fabricated fork and an id collision in this repo before).
"""
import glob
import importlib.util
import os

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.organization import Organization


VERSIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)


def _load_migration():
    matches = glob.glob(
        os.path.join(VERSIONS_DIR, "*_shadow_repaired_automation_triggers.py")
    )
    assert len(matches) == 1, (
        f"Expected exactly one shadow-repair migration file, found {matches}"
    )
    path = matches[0]
    module_name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_rule(db: Session, org: Organization, **overrides) -> AutomationRule:
    defaults = dict(
        organization_id=org.id,
        name="Test Rule",
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50},
        actions=[{"type": "notify", "config": {}}],
        mode="active",
    )
    defaults.update(overrides)
    rule = AutomationRule(**defaults)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _apply_upgrade(db: Session, migration) -> None:
    conn = db.connection()
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        migration.upgrade()
    db.commit()


def _apply_downgrade(db: Session, migration) -> None:
    conn = db.connection()
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        migration.downgrade()
    db.commit()


class TestShadowRepairMigrationUpgrade:
    def test_active_feedback_category_match_becomes_shadow(
        self, db: Session, test_organization: Organization
    ):
        migration = _load_migration()
        rule = _make_rule(
            db, test_organization,
            trigger_type="feedback_category_match",
            mode="active",
        )
        rule_id = rule.id

        _apply_upgrade(db, migration)

        fetched = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
        assert fetched.mode == "shadow"

    def test_active_sentiment_pattern_becomes_shadow(
        self, db: Session, test_organization: Organization
    ):
        migration = _load_migration()
        rule = _make_rule(
            db, test_organization,
            trigger_type="sentiment_pattern",
            mode="active",
        )
        rule_id = rule.id

        _apply_upgrade(db, migration)

        fetched = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
        assert fetched.mode == "shadow"

    def test_active_health_score_threshold_stays_active(
        self, db: Session, test_organization: Organization
    ):
        """Rules on unrelated trigger types have been firing correctly all
        along and must not be disturbed by this migration."""
        migration = _load_migration()
        rule = _make_rule(
            db, test_organization,
            trigger_type="health_score_threshold",
            mode="active",
        )
        rule_id = rule.id

        _apply_upgrade(db, migration)

        fetched = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
        assert fetched.mode == "active"

    def test_off_feedback_category_match_stays_off(
        self, db: Session, test_organization: Organization
    ):
        migration = _load_migration()
        rule = _make_rule(
            db, test_organization,
            trigger_type="feedback_category_match",
            mode="off",
        )
        rule_id = rule.id

        _apply_upgrade(db, migration)

        fetched = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
        assert fetched.mode == "off"

    def test_shadow_sentiment_pattern_stays_shadow(
        self, db: Session, test_organization: Organization
    ):
        migration = _load_migration()
        rule = _make_rule(
            db, test_organization,
            trigger_type="sentiment_pattern",
            mode="shadow",
        )
        rule_id = rule.id

        _apply_upgrade(db, migration)

        fetched = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
        assert fetched.mode == "shadow"


class TestShadowRepairMigrationDowngrade:
    def test_downgrade_is_a_noop(self, db: Session, test_organization: Organization):
        """
        downgrade() must not re-activate anything it moved to shadow — that
        would silently re-arm automations an operator may have deliberately
        left in shadow after reviewing them. See the migration's docstring.
        """
        migration = _load_migration()
        rule = _make_rule(
            db, test_organization,
            trigger_type="feedback_category_match",
            mode="active",
        )
        rule_id = rule.id

        _apply_upgrade(db, migration)
        fetched = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
        assert fetched.mode == "shadow"

        _apply_downgrade(db, migration)
        fetched = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
        assert fetched.mode == "shadow", "downgrade() must be a no-op"
