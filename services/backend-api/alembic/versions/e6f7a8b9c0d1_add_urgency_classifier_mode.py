"""add_urgency_classifier_mode

Revision ID: e6f7a8b9c0d1
Revises: 3e26b38cbd15
Create Date: 2026-07-14 00:00:00.000000

urgency-classifier-head — data-and-config aspect. Adds
org_ai_config.urgency_classifier_mode (VARCHAR(20) NULL DEFAULT 'off'),
independent of the existing classifier_mode (sentiment) and
category_classifier_mode columns. Mechanical copy of the
b3c4d5e6f7a8_add_category_classifier_mode migration. No other schema
change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, None] = '3e26b38cbd15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "org_ai_config",
        sa.Column("urgency_classifier_mode", sa.String(20), nullable=True, server_default="off"),
    )


def downgrade() -> None:
    op.drop_column("org_ai_config", "urgency_classifier_mode")
