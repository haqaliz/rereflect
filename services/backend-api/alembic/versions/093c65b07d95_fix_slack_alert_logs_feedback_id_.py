"""fix slack_alert_logs feedback_id ondelete set null

Revision ID: 093c65b07d95
Revises: d3e4f5g6h7i8
Create Date: 2026-02-13 03:11:17.940274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '093c65b07d95'
down_revision: Union[str, None] = 'd3e4f5g6h7i8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        'slack_alert_logs_feedback_id_fkey',
        'slack_alert_logs',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'slack_alert_logs_feedback_id_fkey',
        'slack_alert_logs',
        'feedback_items',
        ['feedback_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'slack_alert_logs_feedback_id_fkey',
        'slack_alert_logs',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'slack_alert_logs_feedback_id_fkey',
        'slack_alert_logs',
        'feedback_items',
        ['feedback_id'],
        ['id'],
    )
