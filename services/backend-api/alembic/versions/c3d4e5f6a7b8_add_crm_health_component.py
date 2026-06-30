"""add_crm_health_component

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-30 00:00:00.000000

Adds the opt-in CRM health component:
  - org_ai_config.health_weight_crm     INTEGER NOT NULL DEFAULT 0
  - customer_health_scores.crm_component  FLOAT NULL
  - customer_health_history.crm_component FLOAT NULL

With health_weight_crm defaulting to 0, no existing health scores change.
crm_component encodes renewal-proximity risk drawn from crm_enrichment;
it falls back to 50.0 (neutral) when no crm_enrichment row exists.

down_revision verified: alembic heads → b2c3d4e5f6a7 (add_crm_enrichment_table,
hubspot-sync aspect). Third chained migration in the hubspot-crm-enrichment
feature chain.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Opt-in CRM weight column on the config table (NOT NULL DEFAULT 0)
    op.add_column(
        'org_ai_config',
        sa.Column('health_weight_crm', sa.Integer(), nullable=False, server_default='0'),
    )

    # 2. CRM component snapshot on health scores table (nullable — no backfill needed)
    op.add_column(
        'customer_health_scores',
        sa.Column('crm_component', sa.Float(), nullable=True),
    )

    # 3. CRM component snapshot on history table (nullable — pre-feature rows stay null)
    op.add_column(
        'customer_health_history',
        sa.Column('crm_component', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('customer_health_history', 'crm_component')
    op.drop_column('customer_health_scores', 'crm_component')
    op.drop_column('org_ai_config', 'health_weight_crm')
