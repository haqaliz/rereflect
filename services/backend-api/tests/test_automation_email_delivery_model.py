"""
TDD tests for the AutomationEmailDelivery model (automation-send-customer-email,
action-core aspect, Phase A).

The model is the audit row for one automation `send_customer_email` action:
`queued` -> `sent | skipped | failed` (the worker task owns the terminal
transition; the backend only ever writes `queued` on the happy path or
`skipped` on the no-key path).

Mirrors the model-level test style of tests/test_asana_webhook_migration.py:
uses the `db` fixture (schema built via Base.metadata.create_all) rather than
running the real Alembic chain; the migration in
alembic/versions/a2b3c4d5e6f7_add_automation_email_deliveries.py is
hand-verified separately per the plan's Validation step.

NOTE (reconciled decision): the column set deliberately has NO
`automation_execution_id` — the execution log is written AFTER actions run on
every evaluator, so it can never be known at row-creation time. The deliveries
read surface is scoped by `rule_id` instead.
"""
import sqlalchemy as sa
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.automation_rule import AutomationRule
from src.models.automation_email_delivery import AutomationEmailDelivery


class TestAutomationEmailDeliveryModel:

    def test_table_name_is_automation_email_deliveries(self):
        assert AutomationEmailDelivery.__tablename__ == "automation_email_deliveries"

    def test_required_columns_exist(self):
        columns = set(AutomationEmailDelivery.__table__.columns.keys())
        assert {
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
        }.issubset(columns)

    def test_no_automation_execution_id_column(self):
        """Reconciled contract: no automation_execution_id on the row (the
        execution log is written after actions run, so the id is never
        knowable at creation time)."""
        assert "automation_execution_id" not in AutomationEmailDelivery.__table__.columns

    def test_id_is_integer_pk(self):
        column = AutomationEmailDelivery.__table__.columns["id"]
        assert isinstance(column.type, sa.Integer)
        assert column.primary_key is True

    def test_status_defaults_queued(self, db: Session, test_organization: Organization):
        rule = self._make_rule(db, test_organization.id)
        delivery = AutomationEmailDelivery(
            organization_id=test_organization.id,
            rule_id=rule.id,
            customer_email="c@x.com",
            to_email="c@x.com",
            template_key="re_engagement",
            subject="We'd love to hear from you",
            body="Hi c@x.com,",
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)

        assert delivery.status == "queued"
        column = AutomationEmailDelivery.__table__.columns["status"]
        assert column.default.arg == "queued"
        assert column.server_default.arg == "queued"

    def test_reason_nullable(self, db: Session, test_organization: Organization):
        rule = self._make_rule(db, test_organization.id)
        delivery = AutomationEmailDelivery(
            organization_id=test_organization.id,
            rule_id=rule.id,
            customer_email="c@x.com",
            to_email="c@x.com",
            template_key="re_engagement",
            subject="S",
            body="B",
            reason=None,
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        assert delivery.reason is None

        delivery.reason = "email not configured"
        db.commit()
        db.refresh(delivery)
        assert delivery.reason == "email not configured"

        delivery.reason = None
        db.commit()
        db.refresh(delivery)
        assert delivery.reason is None

    def test_org_and_rule_foreign_keys(self, db: Session, test_organization: Organization):
        rule = self._make_rule(db, test_organization.id)
        delivery = AutomationEmailDelivery(
            organization_id=test_organization.id,
            rule_id=rule.id,
            customer_email="c@x.com",
            to_email="c@x.com",
            template_key="re_engagement",
            subject="S",
            body="B",
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)

        assert delivery.organization_id == test_organization.id
        assert delivery.rule_id == rule.id

        rule_fk = AutomationEmailDelivery.__table__.columns["rule_id"].foreign_keys
        assert len(rule_fk) == 1
        assert next(iter(rule_fk)).target_fullname == "automation_rules.id"

    def test_row_round_trips_rendered_content(self, db: Session, test_organization: Organization):
        rule = self._make_rule(db, test_organization.id)
        delivery = AutomationEmailDelivery(
            organization_id=test_organization.id,
            rule_id=rule.id,
            customer_email="CUSTOMER@X.COM",
            to_email="customer@x.com",
            template_key="weekly_digest_entry",
            subject="Your weekly Acme digest",
            body="Hi Alice,\nHere is what happened in Acme this week.",
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)

        assert delivery.template_key == "weekly_digest_entry"
        assert delivery.subject == "Your weekly Acme digest"
        assert delivery.body == "Hi Alice,\nHere is what happened in Acme this week."
        assert delivery.customer_email == "CUSTOMER@X.COM"
        assert delivery.to_email == "customer@x.com"

    def test_delivery_index_on_org_created(self):
        indexes = {
            index.name: index for index in AutomationEmailDelivery.__table__.indexes
        }
        assert "ix_automation_email_deliveries_org_created" in indexes
        index = indexes["ix_automation_email_deliveries_org_created"]
        assert {col.name for col in index.columns} == {"organization_id", "created_at"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_rule(db: Session, org_id: int) -> AutomationRule:
        rule = AutomationRule(
            organization_id=org_id,
            name="Email Rule",
            trigger_type="health_score_threshold",
            trigger_config={"threshold": 30, "direction": "below"},
            actions=[{"type": "send_customer_email", "config": {"template": "re_engagement"}}],
            mode="active",
            cooldown_hours=24,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule