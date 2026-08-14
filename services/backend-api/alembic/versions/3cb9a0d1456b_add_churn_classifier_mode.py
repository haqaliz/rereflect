"""add_churn_classifier_mode

Revision ID: 3cb9a0d1456b
Revises: f6a7b8c9d0e1
Create Date: 2026-08-14 03:55:59.883435

per-org-churn-model (churn-predict-seam-resolver, data layer):

  - org_ai_config.churn_classifier_mode   VARCHAR(20) NULL DEFAULT 'off'
  - org_ai_config.churn_autopromote_hold  BOOLEAN NULL DEFAULT false

churn_classifier_mode is the off/shadow/auto triple for the churn classifier
head, independent of the sentiment/category/urgency mode columns (PRD
independent-control). churn_autopromote_hold pauses auto-promotion of the
weekly churn classifier retrain, mirroring the per-type hold flags.

Both default so existing installs behave exactly as before: mode 'off',
hold false.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3cb9a0d1456b'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Per-org churn classifier mode. 'off' | 'shadow' | 'auto'; NULL treated
    #    as 'off' by resolve_classifier (defense in depth, mirrors the other
    #    mode columns). server_default backfills existing rows to 'off'.
    op.add_column(
        'org_ai_config',
        sa.Column('churn_classifier_mode', sa.String(20), nullable=True, server_default='off'),
    )

    # 2. Per-type "pause auto-promotion" hold for the churn classifier head.
    #    Default false = existing installs auto-promote exactly as before
    #    (mirrors sentiment/category/urgency_autopromote_hold).
    op.add_column(
        'org_ai_config',
        sa.Column('churn_autopromote_hold', sa.Boolean(), nullable=True, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('org_ai_config', 'churn_autopromote_hold')
    op.drop_column('org_ai_config', 'churn_classifier_mode')
