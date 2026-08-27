"""playbook tasks table

Revision ID: 0bf182dad44d
Revises: fb57e62a2820
Create Date: 2026-08-27 02:57:08.281148

playbook-action-types M3 — durable follow-up tasks created by
create_task / schedule_task playbook actions. Write-only in v1 (no
lifecycle endpoints yet); the execution-log surface is the visibility.

Compatible with both PostgreSQL (production) and SQLite (tests).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0bf182dad44d'
down_revision: Union[str, None] = 'fb57e62a2820'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbook_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("playbook_execution_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_playbook_tasks_org_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["playbook_execution_id"],
            ["churn_playbook_executions.id"],
            name="fk_playbook_tasks_playbook_execution_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_playbook_tasks_id",
        "playbook_tasks",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_playbook_tasks_org",
        "playbook_tasks",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_playbook_tasks_org_email",
        "playbook_tasks",
        ["organization_id", "customer_email"],
        unique=False,
    )
    op.create_index(
        "ix_playbook_tasks_org_status",
        "playbook_tasks",
        ["organization_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_playbook_tasks_org_status", table_name="playbook_tasks")
    op.drop_index("ix_playbook_tasks_org_email", table_name="playbook_tasks")
    op.drop_index("ix_playbook_tasks_org", table_name="playbook_tasks")
    op.drop_index("ix_playbook_tasks_id", table_name="playbook_tasks")
    op.drop_table("playbook_tasks")
