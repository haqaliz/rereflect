"""
TDD tests — playbook-action-types PRD, aspect `playbook-tasks`, Phase 1.

Coverage (AC7, model half): PlaybookTask columns exist with the right
types/nullability, description is required, priority/status default to
medium/open, due_at/completed_at are nullable, and the org/customer/
playbook-execution linkages are real FKs.
"""
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.churn_playbook import ChurnPlaybook, ChurnPlaybookExecution
from src.models.organization import Organization
from src.models.playbook_task import PlaybookTask


class TestPlaybookTaskColumns:
    def test_table_and_all_columns_exist(self):
        columns = {c.name: c for c in PlaybookTask.__table__.columns}

        assert PlaybookTask.__tablename__ == "playbook_tasks"
        for name in [
            "id",
            "organization_id",
            "customer_email",
            "description",
            "due_at",
            "priority",
            "status",
            "playbook_execution_id",
            "created_at",
            "completed_at",
        ]:
            assert name in columns, f"missing column {name}"

        assert columns["description"].type.python_type is str
        assert columns["priority"].type.length == 10
        assert columns["status"].type.length == 10

    def test_indexes_exist(self):
        indexes = {ix.name: ix for ix in PlaybookTask.__table__.indexes}

        assert "ix_playbook_tasks_org" in indexes
        assert "ix_playbook_tasks_org_email" in indexes
        assert "ix_playbook_tasks_org_status" in indexes

    def test_description_is_required(self, db: Session, test_organization: Organization):
        task = PlaybookTask(
            organization_id=test_organization.id,
            customer_email="no-desc@example.com",
        )
        db.add(task)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_priority_and_status_defaults(self, db: Session, test_organization: Organization):
        task = PlaybookTask(
            organization_id=test_organization.id,
            customer_email="defaults@example.com",
            description="Follow up on churn risk",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        assert task.priority == "medium"
        assert task.status == "open"
        assert task.created_at is not None

    def test_due_at_and_completed_at_nullable(self, db: Session, test_organization: Organization):
        task = PlaybookTask(
            organization_id=test_organization.id,
            customer_email="nullable@example.com",
            description="No due date yet",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        assert task.due_at is None
        assert task.completed_at is None

        task.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
        assert task.completed_at is not None


class TestPlaybookTaskLinkage:
    def test_org_and_customer_linkage(self, db: Session, test_organization: Organization):
        task = PlaybookTask(
            organization_id=test_organization.id,
            customer_email="linked@example.com",
            description="Reach out to customer",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        assert task.organization_id == test_organization.id
        assert task.customer_email == "linked@example.com"

        org_fk = next(
            fk for fk in PlaybookTask.__table__.foreign_keys if fk.parent.name == "organization_id"
        )
        assert org_fk.target_fullname == "organizations.id"

    def test_playbook_execution_linkage(self, db: Session, test_organization: Organization):
        playbook = ChurnPlaybook(
            organization_id=test_organization.id,
            name="Retention playbook",
            probability_min=0.5,
            probability_max=0.9,
            action_sequence=[],
        )
        db.add(playbook)
        db.commit()
        db.refresh(playbook)

        execution = ChurnPlaybookExecution(
            playbook_id=playbook.id,
            organization_id=test_organization.id,
            customer_email="exec@example.com",
            triggered_by="manual",
            status="running",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        task = PlaybookTask(
            organization_id=test_organization.id,
            customer_email="exec@example.com",
            description="Task spawned by a run",
            playbook_execution_id=execution.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        assert task.playbook_execution_id == execution.id

        execution_fk = next(
            fk
            for fk in PlaybookTask.__table__.foreign_keys
            if fk.parent.name == "playbook_execution_id"
        )
        assert execution_fk.target_fullname == "churn_playbook_executions.id"