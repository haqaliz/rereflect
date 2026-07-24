"""org_ai_config autopromote_hold flags

Revision ID: 719deb6ac0a0
Revises: 0a3382154c27
Create Date: 2026-07-24 19:48:29.446881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '719deb6ac0a0'
down_revision: Union[str, None] = '0a3382154c27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-type "pause auto-promotion" hold for the M5.2 corrections classifiers.
    # Nullable + server_default false so existing rows/installs auto-promote as
    # before (classifier-model-versioning-rollback, M1).
    for col in (
        "sentiment_autopromote_hold",
        "category_autopromote_hold",
        "urgency_autopromote_hold",
    ):
        op.add_column(
            "org_ai_config",
            sa.Column(col, sa.Boolean(), nullable=True, server_default=sa.false()),
        )


def downgrade() -> None:
    for col in (
        "urgency_autopromote_hold",
        "category_autopromote_hold",
        "sentiment_autopromote_hold",
    ):
        op.drop_column("org_ai_config", col)
