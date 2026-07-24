"""add_usage_churn_label_config

Revision ID: 0a3382154c27
Revises: a1c2d3e4f5a6
Create Date: 2026-07-23 00:00:00.000000

usage-decline-churn-labels — config-and-migration aspect. Adds
org_ai_config.usage_churn_labels_mode (VARCHAR(20) NULL DEFAULT 'off') and
org_ai_config.usage_churn_label_config (JSON NULL). 'off' | 'shadow' |
'active' — NOT the classifier off/shadow/auto triple (see plan.md §2):
this gates writing rows into the churn-suggestion review queue, mirroring
AutomationRule.mode. Mechanical copy of the
e6f7a8b9c0d1_add_urgency_classifier_mode migration. No other schema change.

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`a1c2d3e4f5a6 (head)`. This revision chains directly off that sole
verified head — no merge revision, no static parse.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0a3382154c27'
down_revision: Union[str, None] = 'a1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "org_ai_config",
        sa.Column("usage_churn_labels_mode", sa.String(20), nullable=True, server_default="off"),
    )
    op.add_column(
        "org_ai_config",
        sa.Column("usage_churn_label_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("org_ai_config", "usage_churn_label_config")
    op.drop_column("org_ai_config", "usage_churn_labels_mode")
