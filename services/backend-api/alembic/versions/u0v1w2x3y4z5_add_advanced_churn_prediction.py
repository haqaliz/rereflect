"""add_advanced_churn_prediction

Revision ID: u0v1w2x3y4z5
Revises: t9u0v1w2x3y4
Create Date: 2026-05-20 00:00:00.000000

M4.1 — Advanced Churn Prediction foundation.

Creates five new tables for churn label collection, model calibration
versioning, backtest observability, and reusable prevention playbooks:

  customer_churn_events       — manual + CSV + auto-suggested churn labels
  churn_calibration_models    — versioned isotonic regression models
  churn_backtest_runs         — weekly refit observability history
  churn_playbooks             — reusable probability-bound prevention plans
  churn_playbook_executions   — audit log for playbook runs

Adds seven new columns to customer_health_scores so that every customer
row can carry a calibrated 30-day churn probability + 90% CI, a
time-to-churn bucket, a reference to the model that computed it, and a
winback flag.

Backfills has_potential_winback = FALSE on all existing rows before
converting the column to NOT NULL.

Compatible with both PostgreSQL (production) and SQLite (tests).
All JSON columns use sa.JSON() — rendered as JSONB on PostgreSQL via the
SQLAlchemy PostgreSQL dialect without changing the migration source.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "u0v1w2x3y4z5"
down_revision: Union[str, None] = "t9u0v1w2x3y4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. customer_churn_events
    #    Manual + CSV-imported + auto-suggested churn labels.
    #    Drives the calibration training set.
    # ------------------------------------------------------------------
    op.create_table(
        "customer_churn_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("churned_at", sa.DateTime(), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("recovered_at", sa.DateTime(), nullable=True),
        sa.Column("marked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_customer_churn_events_org_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["marked_by_user_id"],
            ["users.id"],
            name="fk_customer_churn_events_marked_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "customer_email",
            "churned_at",
            name="uq_churn_event_org_email_date",
        ),
    )
    op.create_index(
        "ix_customer_churn_events_id",
        "customer_churn_events",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_churn_event_org_date",
        "customer_churn_events",
        ["organization_id", "churned_at"],
        unique=False,
    )
    op.create_index(
        "ix_churn_event_org_email",
        "customer_churn_events",
        ["organization_id", "customer_email"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 2. churn_calibration_models
    #    Versioned isotonic regression models.
    #    organization_id IS NULL means global fallback model.
    # ------------------------------------------------------------------
    op.create_table(
        "churn_calibration_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("model_json", sa.JSON(), nullable=False),
        sa.Column("label_count", sa.Integer(), nullable=False),
        sa.Column("positive_count", sa.Integer(), nullable=False),
        sa.Column("precision", sa.Numeric(5, 4), nullable=True),
        sa.Column("recall", sa.Numeric(5, 4), nullable=True),
        sa.Column("f1", sa.Numeric(5, 4), nullable=True),
        sa.Column("auc", sa.Numeric(5, 4), nullable=True),
        sa.Column("threshold_bands", sa.JSON(), nullable=False),
        sa.Column(
            "fit_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_churn_calibration_models_org_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_churn_calibration_models_id",
        "churn_calibration_models",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_churn_cal_model_org_fit",
        "churn_calibration_models",
        ["organization_id", "fit_at"],
        unique=False,
    )
    # Partial unique index: at most one active model per org_id value.
    # SQLite uses sqlite_where; PostgreSQL uses postgresql_where.
    # We create it twice — only one will apply at runtime.
    op.create_index(
        "uq_churn_cal_model_one_active_per_org",
        "churn_calibration_models",
        ["organization_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active = TRUE"),
    )

    # ------------------------------------------------------------------
    # 3. churn_backtest_runs
    #    Weekly refit observability — one row per refit execution.
    # ------------------------------------------------------------------
    op.create_table(
        "churn_backtest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("calibration_model_id", sa.Integer(), nullable=False),
        sa.Column(
            "run_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column("label_count", sa.Integer(), nullable=False),
        sa.Column("precision", sa.Numeric(5, 4), nullable=True),
        sa.Column("recall", sa.Numeric(5, 4), nullable=True),
        sa.Column("f1", sa.Numeric(5, 4), nullable=True),
        sa.Column("auc", sa.Numeric(5, 4), nullable=True),
        sa.Column("optimal_threshold", sa.Numeric(5, 4), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_churn_backtest_runs_org_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["calibration_model_id"],
            ["churn_calibration_models.id"],
            name="fk_churn_backtest_runs_cal_model_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_churn_backtest_runs_id",
        "churn_backtest_runs",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_churn_backtest_org_run_at",
        "churn_backtest_runs",
        ["organization_id", "run_at"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 4. churn_playbooks
    #    Reusable prevention plans with probability range binding.
    # ------------------------------------------------------------------
    op.create_table(
        "churn_playbooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("probability_min", sa.Numeric(3, 2), nullable=False),
        sa.Column("probability_max", sa.Numeric(3, 2), nullable=False),
        sa.Column("action_sequence", sa.JSON(), nullable=False),
        sa.Column(
            "is_template",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("source_template_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "probability_min < probability_max",
            name="ck_playbook_probability_range",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_churn_playbooks_org_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_template_id"],
            ["churn_playbooks.id"],
            name="fk_churn_playbooks_source_template_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_churn_playbooks_id",
        "churn_playbooks",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_churn_playbook_org_active",
        "churn_playbooks",
        ["organization_id", "is_active"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 5. churn_playbook_executions
    #    Audit log + status tracking for playbook runs.
    #    Purged after 90 days by a Celery Beat task.
    # ------------------------------------------------------------------
    op.create_table(
        "churn_playbook_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("playbook_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("triggered_by", sa.String(40), nullable=False),
        sa.Column("triggered_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "action_log",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["playbook_id"],
            ["churn_playbooks.id"],
            name="fk_churn_playbook_execs_playbook_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_churn_playbook_execs_org_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
            name="fk_churn_playbook_execs_triggered_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_churn_playbook_executions_id",
        "churn_playbook_executions",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_playbook_exec_org_created",
        "churn_playbook_executions",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_playbook_exec_playbook_created",
        "churn_playbook_executions",
        ["playbook_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_playbook_exec_email_created",
        "churn_playbook_executions",
        ["customer_email", "created_at"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 6. New columns on customer_health_scores
    # ------------------------------------------------------------------
    op.add_column(
        "customer_health_scores",
        sa.Column("churn_probability", sa.Numeric(5, 4), nullable=True),
    )
    op.add_column(
        "customer_health_scores",
        sa.Column("churn_probability_low", sa.Numeric(5, 4), nullable=True),
    )
    op.add_column(
        "customer_health_scores",
        sa.Column("churn_probability_high", sa.Numeric(5, 4), nullable=True),
    )
    op.add_column(
        "customer_health_scores",
        sa.Column("time_to_churn_bucket", sa.String(20), nullable=True),
    )
    op.add_column(
        "customer_health_scores",
        sa.Column("calibration_model_id", sa.Integer(), nullable=True),
    )
    # FK from customer_health_scores.calibration_model_id to churn_calibration_models.id.
    # op.create_foreign_key uses ALTER TABLE ADD CONSTRAINT which SQLite does not support.
    # We add it only on PostgreSQL; SQLite ignores FK constraints unless PRAGMA is enabled.
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_customer_health_scores_cal_model_id",
            "customer_health_scores",
            "churn_calibration_models",
            ["calibration_model_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.add_column(
        "customer_health_scores",
        sa.Column("probability_computed_at", sa.DateTime(), nullable=True),
    )
    # Add has_potential_winback as nullable first so the backfill UPDATE can run.
    op.add_column(
        "customer_health_scores",
        sa.Column("has_potential_winback", sa.Boolean(), nullable=True),
    )
    # Backfill: set FALSE on all existing rows before making NOT NULL.
    op.execute(
        "UPDATE customer_health_scores"
        " SET has_potential_winback = FALSE"
        " WHERE has_potential_winback IS NULL"
    )
    # Enforce NOT NULL + server_default (batch mode for SQLite compatibility).
    with op.batch_alter_table("customer_health_scores") as batch_op:
        batch_op.alter_column(
            "has_potential_winback",
            nullable=False,
            server_default=sa.false(),
        )


def downgrade() -> None:
    # Reverse order: executions → playbooks → backtest → calibration → events
    # then revert customer_health_scores columns.

    # ------------------------------------------------------------------
    # Revert customer_health_scores columns
    # Drop FK first (PostgreSQL requires it before dropping the column).
    # SQLite doesn't support DROP CONSTRAINT so we skip it there.
    # ------------------------------------------------------------------
    conn = op.get_bind()
    if conn.dialect.name != "sqlite":
        op.drop_constraint(
            "fk_customer_health_scores_cal_model_id",
            "customer_health_scores",
            type_="foreignkey",
        )
    op.drop_column("customer_health_scores", "has_potential_winback")
    op.drop_column("customer_health_scores", "probability_computed_at")
    op.drop_column("customer_health_scores", "calibration_model_id")
    op.drop_column("customer_health_scores", "time_to_churn_bucket")
    op.drop_column("customer_health_scores", "churn_probability_high")
    op.drop_column("customer_health_scores", "churn_probability_low")
    op.drop_column("customer_health_scores", "churn_probability")

    # ------------------------------------------------------------------
    # churn_playbook_executions
    # ------------------------------------------------------------------
    op.drop_index(
        "ix_playbook_exec_email_created",
        table_name="churn_playbook_executions",
    )
    op.drop_index(
        "ix_playbook_exec_playbook_created",
        table_name="churn_playbook_executions",
    )
    op.drop_index(
        "ix_playbook_exec_org_created",
        table_name="churn_playbook_executions",
    )
    op.drop_index(
        "ix_churn_playbook_executions_id",
        table_name="churn_playbook_executions",
    )
    op.drop_table("churn_playbook_executions")

    # ------------------------------------------------------------------
    # churn_playbooks
    # ------------------------------------------------------------------
    op.drop_index("ix_churn_playbook_org_active", table_name="churn_playbooks")
    op.drop_index("ix_churn_playbooks_id", table_name="churn_playbooks")
    op.drop_table("churn_playbooks")

    # ------------------------------------------------------------------
    # churn_backtest_runs
    # ------------------------------------------------------------------
    op.drop_index(
        "ix_churn_backtest_org_run_at", table_name="churn_backtest_runs"
    )
    op.drop_index(
        "ix_churn_backtest_runs_id", table_name="churn_backtest_runs"
    )
    op.drop_table("churn_backtest_runs")

    # ------------------------------------------------------------------
    # churn_calibration_models
    # ------------------------------------------------------------------
    op.drop_index(
        "uq_churn_cal_model_one_active_per_org",
        table_name="churn_calibration_models",
    )
    op.drop_index(
        "ix_churn_cal_model_org_fit",
        table_name="churn_calibration_models",
    )
    op.drop_index(
        "ix_churn_calibration_models_id",
        table_name="churn_calibration_models",
    )
    op.drop_table("churn_calibration_models")

    # ------------------------------------------------------------------
    # customer_churn_events
    # ------------------------------------------------------------------
    op.drop_index(
        "ix_churn_event_org_email",
        table_name="customer_churn_events",
    )
    op.drop_index(
        "ix_churn_event_org_date",
        table_name="customer_churn_events",
    )
    op.drop_index(
        "ix_customer_churn_events_id",
        table_name="customer_churn_events",
    )
    op.drop_table("customer_churn_events")
