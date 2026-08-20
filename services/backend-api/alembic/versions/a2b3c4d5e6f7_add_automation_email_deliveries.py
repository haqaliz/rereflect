"""add_automation_email_deliveries

Revision ID: a2b3c4d5e6f7
Revises: f5a6b7c8d9e0
Create Date: 2026-08-19 00:00:00.000000

automation-send-customer-email (action-core aspect, M3):

  - automation_email_deliveries — audit row for one automation
    send_customer_email action:
    id (Integer PK), organization_id (FK, ondelete CASCADE), rule_id (FK,
    ondelete CASCADE), customer_email, to_email, template_key, subject, body,
    status ('queued' default), reason (nullable), created_at, updated_at.

Deliberately NO automation_execution_id column: the execution log is written
after actions run on every evaluator, so the execution id is never knowable
at row-creation time; the deliveries read surface is scoped by rule_id.

The worker task (worker-mirrors aspect) owns the queued -> sent|skipped|failed
terminal transition; the backend only ever writes queued (happy) or skipped
(no-key).

Additive table only — safe on existing data, symmetric upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'automation_email_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'organization_id',
            sa.Integer(),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'rule_id',
            sa.Integer(),
            sa.ForeignKey('automation_rules.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('customer_email', sa.String(255), nullable=False),
        sa.Column('to_email', sa.String(255), nullable=False),
        sa.Column('template_key', sa.String(50), nullable=False),
        sa.Column('subject', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index(
        'ix_automation_email_deliveries_organization_id',
        'automation_email_deliveries',
        ['organization_id'],
    )
    op.create_index(
        'ix_automation_email_deliveries_rule_id',
        'automation_email_deliveries',
        ['rule_id'],
    )
    op.create_index(
        'ix_automation_email_deliveries_org_created',
        'automation_email_deliveries',
        ['organization_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_automation_email_deliveries_org_created',
        table_name='automation_email_deliveries',
    )
    op.drop_index(
        'ix_automation_email_deliveries_rule_id',
        table_name='automation_email_deliveries',
    )
    op.drop_index(
        'ix_automation_email_deliveries_organization_id',
        table_name='automation_email_deliveries',
    )
    op.drop_table('automation_email_deliveries')