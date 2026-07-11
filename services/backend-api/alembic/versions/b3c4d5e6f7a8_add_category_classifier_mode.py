"""add_category_classifier_mode

Revision ID: b3c4d5e6f7a8
Revises: v2w3x4y5z6a7
Create Date: 2026-07-11 00:00:00.000000

M5.2 v2 per-org category classifier — data-and-config aspect. Adds
org_ai_config.category_classifier_mode (VARCHAR(20) NULL DEFAULT 'off'),
independent of the existing classifier_mode (sentiment) column. No other
schema change: org_classifier_models / org_classifier_eval_runs / ai_corrections
are already classifier_type-generic (see v2w3x4y5z6a7 and s8t9u0v1w2x3).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'v2w3x4y5z6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "org_ai_config",
        sa.Column("category_classifier_mode", sa.String(20), nullable=True, server_default="off"),
    )


def downgrade() -> None:
    op.drop_column("org_ai_config", "category_classifier_mode")
