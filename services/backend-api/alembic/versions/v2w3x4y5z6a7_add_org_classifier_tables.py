"""add_org_classifier_tables

Revision ID: v2w3x4y5z6a7
Revises: 6ad1dc4335f1
Create Date: 2026-07-10 14:30:00.000000

M5.2 per-org self-improving corrections classifier — data layer.
Creates org_classifier_models (versioned JSON artifact; one active per
(organization_id, classifier_type) via a dialect-aware partial-unique index)
and org_classifier_eval_runs (shadow-A/B history), and adds
org_ai_config.classifier_mode (VARCHAR(20) NULL DEFAULT 'off').
JSON artifact only — never pickle. Compatible with PostgreSQL + SQLite.

NOTE: the data-layer plan (plan_20260710.md) originally specified revision
id 'y4z5a6b7c8d9', but that id was already in use by an unrelated,
previously-merged migration (y4z5a6b7c8d9_add_embedding_provider_dim_to_mappings,
2026-06-28). Renamed to 'v2w3x4y5z6a7' to avoid a duplicate-revision cycle
in the Alembic graph. down_revision is unchanged ('6ad1dc4335f1', the
current single head) per the plan's locked constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'v2w3x4y5z6a7'
down_revision: Union[str, None] = '6ad1dc4335f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_classifier_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("classifier_type", sa.String(30), nullable=False),
        sa.Column("model_json", sa.JSON(), nullable=False),
        sa.Column("label_count", sa.Integer(), nullable=False),
        sa.Column("precision", sa.Numeric(5, 4), nullable=True),
        sa.Column("recall", sa.Numeric(5, 4), nullable=True),
        sa.Column("macro_f1", sa.Numeric(5, 4), nullable=True),
        sa.Column("accuracy", sa.Numeric(5, 4), nullable=True),
        sa.Column("fit_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_org_classifier_models_org_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_classifier_models_id", "org_classifier_models", ["id"])
    op.create_index(
        "ix_org_classifier_model_org_type_fit", "org_classifier_models",
        ["organization_id", "classifier_type", "fit_at"],
    )
    # Partial unique index: at most one active model per (org_id, classifier_type) pair.
    # SQLite uses sqlite_where; PostgreSQL uses postgresql_where.
    op.create_index(
        "uq_org_classifier_one_active", "org_classifier_models",
        ["organization_id", "classifier_type"], unique=True,
        sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.create_table(
        "org_classifier_eval_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("classifier_model_id", sa.Integer(), nullable=True),
        sa.Column("classifier_type", sa.String(30), nullable=False),
        sa.Column("incumbent_macro_f1", sa.Numeric(5, 4), nullable=True),
        sa.Column("challenger_macro_f1", sa.Numeric(5, 4), nullable=True),
        sa.Column("macro_f1_delta", sa.Numeric(5, 4), nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("n", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_org_classifier_eval_runs_org_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["classifier_model_id"], ["org_classifier_models.id"],
            name="fk_org_classifier_eval_runs_model_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_classifier_eval_runs_id", "org_classifier_eval_runs", ["id"])
    op.create_index(
        "ix_org_classifier_eval_org_type_created", "org_classifier_eval_runs",
        ["organization_id", "classifier_type", "created_at"],
    )

    op.add_column(
        "org_ai_config",
        sa.Column("classifier_mode", sa.String(20), nullable=True, server_default="off"),
    )


def downgrade() -> None:
    op.drop_column("org_ai_config", "classifier_mode")
    op.drop_index("ix_org_classifier_eval_org_type_created", table_name="org_classifier_eval_runs")
    op.drop_index("ix_org_classifier_eval_runs_id", table_name="org_classifier_eval_runs")
    op.drop_table("org_classifier_eval_runs")
    op.drop_index("uq_org_classifier_one_active", table_name="org_classifier_models")
    op.drop_index("ix_org_classifier_model_org_type_fit", table_name="org_classifier_models")
    op.drop_index("ix_org_classifier_models_id", table_name="org_classifier_models")
    op.drop_table("org_classifier_models")
