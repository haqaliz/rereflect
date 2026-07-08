"""add segment to customer_health_scores

Adds a `segment` column (nullable String(30)) to `customer_health_scores`
for the rule-based customer segment classifier (at_risk, silent_churner,
dormant, power_user, happy_advocate, new, unsegmented — see
`src/services/segment_service.py`). Also adds a composite index mirroring
the existing `ix_customer_health_risk` precedent, to support org-scoped
filtering by segment.

No data backfill here — this migration only adds the column/index; values
stay null until the ingest path (`update_customer_health`) or the nightly
`recompute_segments` worker task populate them.

Revision ID: 6d7e00e682c7
Revises: a5b6c7d8e9f0
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6d7e00e682c7"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "customer_health_scores",
        sa.Column("segment", sa.String(length=30), nullable=True),
    )
    op.create_index(
        "ix_customer_health_segment",
        "customer_health_scores",
        ["organization_id", "segment"],
    )


def downgrade():
    op.drop_index("ix_customer_health_segment", table_name="customer_health_scores")
    op.drop_column("customer_health_scores", "segment")
