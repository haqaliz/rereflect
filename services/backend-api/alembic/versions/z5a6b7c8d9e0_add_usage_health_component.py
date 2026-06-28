"""add_usage_health_component

Revision ID: z5a6b7c8d9e0
Revises: y4z5a6b7c8d9
Create Date: 2026-06-28 00:00:00.000000

Adds the opt-in usage health component:
  - org_ai_config.health_weight_usage    INTEGER NOT NULL DEFAULT 0
  - customer_health_scores.usage_component   INTEGER NULL
  - customer_health_history.usage_component  INTEGER NULL

With health_weight_usage defaulting to 0, no existing health scores change.
The usage_component value is computed by aspect usage-rollup-and-score and
fetched by _compute_usage_component(); it falls back to 50 (neutral) when the
customer_usage table/row does not exist.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'z5a6b7c8d9e0'
down_revision: Union[str, None] = 'y4z5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Opt-in weight column on the config table (NOT NULL DEFAULT 0)
    op.add_column(
        'org_ai_config',
        sa.Column('health_weight_usage', sa.Integer(), nullable=False, server_default='0'),
    )

    # 2. Usage component snapshot on health scores table (nullable — no backfill needed)
    op.add_column(
        'customer_health_scores',
        sa.Column('usage_component', sa.Integer(), nullable=True),
    )

    # 3. Usage component snapshot on history table (nullable — pre-feature rows stay null)
    op.add_column(
        'customer_health_history',
        sa.Column('usage_component', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('customer_health_history', 'usage_component')
    op.drop_column('customer_health_scores', 'usage_component')
    op.drop_column('org_ai_config', 'health_weight_usage')
