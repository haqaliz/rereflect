"""add tags and cs_owner to customer_health

Adds `tags` (JSON list of strings, nullable, app-level default `[]`) and
`cs_owner_user_id` (nullable FK -> users.id, ondelete=SET NULL) to
`customer_health_scores`, plus a composite index
`ix_customer_health_cs_owner` on (organization_id, cs_owner_user_id) —
segment-actions PRD, aspect `customer-fields-model`. These columns give the
bulk tag/assign-CS-owner actions (separate aspect) something to write, and
are surfaced read-only on the customers list/profile serializers here.

FK note: op.create_foreign_key uses ALTER TABLE ADD CONSTRAINT, which
SQLite does not support outside of batch mode. Tests exercise this
migration against SQLite via direct Operations calls (see
tests/test_migrations_segment_actions.py), so the FK create/drop is
skipped on the sqlite dialect and only applied on PostgreSQL (mirrors the
precedent in u0v1w2x3y4z5_add_advanced_churn_prediction.py for
calibration_model_id).

Revision ID: a6b703d7a303
Revises: 6d7e00e682c7
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a6b703d7a303"
down_revision = "6d7e00e682c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customer_health_scores",
        sa.Column("tags", sa.JSON(), nullable=True),
    )
    op.add_column(
        "customer_health_scores",
        sa.Column("cs_owner_user_id", sa.Integer(), nullable=True),
    )

    # FK from customer_health_scores.cs_owner_user_id to users.id.
    # op.create_foreign_key uses ALTER TABLE ADD CONSTRAINT which SQLite
    # does not support. We add it only on PostgreSQL; SQLite ignores FK
    # constraints unless PRAGMA is enabled (see test-harness notes above).
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_customer_health_cs_owner",
            "customer_health_scores",
            "users",
            ["cs_owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index(
        "ix_customer_health_cs_owner",
        "customer_health_scores",
        ["organization_id", "cs_owner_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_health_cs_owner", table_name="customer_health_scores")

    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        op.drop_constraint(
            "fk_customer_health_cs_owner",
            "customer_health_scores",
            type_="foreignkey",
        )

    op.drop_column("customer_health_scores", "cs_owner_user_id")
    op.drop_column("customer_health_scores", "tags")
