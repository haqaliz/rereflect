"""
TDD migration tests for M4.1 Advanced Churn Prediction.

Strategy
--------
We cannot run the full Alembic chain against SQLite (existing migrations use
PostgreSQL-specific DDL such as op.drop_constraint / FK introspection via
information_schema).

Instead we:

1. Build a *pre-migration* metadata object containing only the subset of
   tables that existed before this migration, WITHOUT the new churn tables
   and WITHOUT the seven new columns on customer_health_scores.

2. Create those tables against a fresh temp-file SQLite database.

3. Apply our migration's upgrade() / downgrade() functions directly via the
   Alembic Operations proxy.

4. Inspect the schema with sqlalchemy.inspect() to verify correctness.

This tests exactly what the migration does in isolation, against a realistic
pre-migration schema, without depending on PostgreSQL DDL in older migrations.

Revision target: ``u0v1w2x3y4z5`` (slug: add_advanced_churn_prediction)
"""

import os
import tempfile
import uuid

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# Import the migration module under test
# ---------------------------------------------------------------------------

import importlib
import sys

VERSIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)
if VERSIONS_DIR not in sys.path:
    sys.path.insert(0, VERSIONS_DIR)

_migration = importlib.import_module(
    "u0v1w2x3y4z5_add_advanced_churn_prediction"
)

# ---------------------------------------------------------------------------
# Pre-migration metadata
# Defines only the tables that existed BEFORE our migration.
# Deliberately excludes the 5 new churn tables and the 7 new columns on
# customer_health_scores.
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

# Minimal organizations table (other columns omitted — not relevant to our migration).
sa.Table(
    "organizations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
    sa.Column("plan", sa.String(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("seat_count", sa.Integer(), nullable=False, server_default="1"),
)

# Minimal users table.
sa.Table(
    "users",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("email", sa.String(), nullable=False),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id")),
    sa.Column("role", sa.String(), nullable=False, server_default="member"),
    sa.Column("password_hash", sa.String(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
)

# customer_health_scores WITHOUT the 7 new M4.1 columns.
sa.Table(
    "customer_health_scores",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("customer_email", sa.String(255), nullable=False),
    sa.Column("customer_name", sa.String(255), nullable=True),
    sa.Column("health_score", sa.Integer(), nullable=False, server_default="50"),
    sa.Column("churn_risk_component", sa.Integer(), server_default="50"),
    sa.Column("sentiment_component", sa.Integer(), server_default="50"),
    sa.Column("resolution_component", sa.Integer(), server_default="50"),
    sa.Column("frequency_component", sa.Integer(), server_default="50"),
    sa.Column("feedback_count", sa.Integer(), server_default="0"),
    sa.Column("last_feedback_at", sa.DateTime(), nullable=True),
    sa.Column("risk_level", sa.String(20), server_default="unknown"),
    sa.Column("confidence_level", sa.String(20), server_default="low"),
    sa.Column("confidence_score", sa.Integer(), server_default="0"),
    sa.Column("is_archived", sa.Boolean(), server_default="0"),
    sa.Column("llm_analysis", sa.Text(), nullable=True),
    sa.Column("llm_analyzed_at", sa.DateTime(), nullable=True),
    sa.Column("llm_analysis_data", sa.JSON(), nullable=True),
    sa.Column("llm_raw_response", sa.JSON(), nullable=True),
    sa.Column("llm_provider", sa.String(20), nullable=True),
    sa.Column("llm_model", sa.String(50), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=True),
    sa.Column("updated_at", sa.DateTime(), nullable=True),
    sa.UniqueConstraint("organization_id", "customer_email", name="ix_customer_health_org_email"),
)


# ---------------------------------------------------------------------------
# Engine factory — temp-file SQLite for proper isolation between tests
# ---------------------------------------------------------------------------


def _make_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )
    engine._test_db_path = path  # type: ignore[attr-defined]
    return engine


def _dispose(engine):
    engine.dispose()
    path = getattr(engine, "_test_db_path", None)
    if path and os.path.exists(path):
        os.unlink(path)


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------


def _apply_upgrade(conn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        _migration.upgrade()


def _apply_downgrade(conn):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        _migration.downgrade()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pre_migration_engine():
    """
    Fresh temp-file SQLite engine with the PRE-MIGRATION schema
    (customer_health_scores without new columns, no churn tables).
    """
    engine = _make_engine()
    _pre_meta.create_all(bind=engine)
    yield engine
    _pre_meta.drop_all(bind=engine)
    _dispose(engine)


@pytest.fixture
def migrated_engine(pre_migration_engine):
    """Pre-migration schema + our upgrade() applied."""
    with pre_migration_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        _apply_upgrade(conn)
    yield pre_migration_engine


# ---------------------------------------------------------------------------
# Test 1: customer_churn_events — table + required columns
# ---------------------------------------------------------------------------


class TestCustomerChurnEventsTable:
    def test_customer_churn_events_table_exists_with_required_columns(
        self, migrated_engine
    ):
        """
        customer_churn_events must exist with all required columns per PRD §3.1:
        id, organization_id, customer_email, churned_at, reason_code,
        reason_text, recovered_at, marked_by_user_id, source,
        created_at, updated_at.
        """
        insp = inspect(migrated_engine)
        assert insp.has_table("customer_churn_events"), (
            "Table 'customer_churn_events' does not exist after migration."
        )

        cols = {c["name"] for c in insp.get_columns("customer_churn_events")}
        required = {
            "id",
            "organization_id",
            "customer_email",
            "churned_at",
            "reason_code",
            "reason_text",
            "recovered_at",
            "marked_by_user_id",
            "source",
            "created_at",
            "updated_at",
        }
        missing = required - cols
        assert not missing, f"Missing columns in customer_churn_events: {missing}"

    def test_customer_churn_events_column_nullability(self, migrated_engine):
        """
        churned_at, reason_code must be NOT NULL.
        reason_text, recovered_at, marked_by_user_id must be nullable.
        """
        insp = inspect(migrated_engine)
        col_map = {
            c["name"]: c
            for c in insp.get_columns("customer_churn_events")
        }
        assert not col_map["churned_at"]["nullable"], "churned_at must be NOT NULL"
        assert not col_map["reason_code"]["nullable"], (
            "reason_code must be NOT NULL"
        )
        assert col_map["reason_text"]["nullable"], "reason_text must be nullable"
        assert col_map["recovered_at"]["nullable"], "recovered_at must be nullable"
        assert col_map["marked_by_user_id"]["nullable"], (
            "marked_by_user_id must be nullable"
        )


# ---------------------------------------------------------------------------
# Test 2: unique constraint on customer_churn_events
# ---------------------------------------------------------------------------


class TestCustomerChurnEventsUniqueConstraint:
    def test_customer_churn_events_unique_constraint(self, migrated_engine):
        """
        UNIQUE (organization_id, customer_email, churned_at) must be enforced.
        """
        row = {
            "organization_id": 999,
            "customer_email": "alice@example.com",
            "churned_at": "2026-03-01 00:00:00",
            "reason_code": "price",
            "source": "manual",
            "created_at": "2026-03-01 00:00:00",
            "updated_at": "2026-03-01 00:00:00",
        }
        insert_sql = text(
            "INSERT INTO customer_churn_events"
            " (organization_id, customer_email, churned_at,"
            "  reason_code, source, created_at, updated_at)"
            " VALUES (:organization_id, :customer_email,"
            "  :churned_at, :reason_code, :source, :created_at, :updated_at)"
        )

        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(insert_sql, row)

        with pytest.raises(IntegrityError):
            with migrated_engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                conn.execute(insert_sql, row)


# ---------------------------------------------------------------------------
# Test 3: indexes on customer_churn_events
# ---------------------------------------------------------------------------


class TestCustomerChurnEventsIndexes:
    def test_customer_churn_events_indexes_exist(self, migrated_engine):
        """
        Two composite indexes:
        ix_churn_event_org_date  → (organization_id, churned_at)
        ix_churn_event_org_email → (organization_id, customer_email)
        """
        insp = inspect(migrated_engine)
        idx_names = {
            i["name"] for i in insp.get_indexes("customer_churn_events")
        }

        assert "ix_churn_event_org_date" in idx_names, (
            f"ix_churn_event_org_date not found in: {idx_names}"
        )
        assert "ix_churn_event_org_email" in idx_names, (
            f"ix_churn_event_org_email not found in: {idx_names}"
        )


# ---------------------------------------------------------------------------
# Test 4: churn_calibration_models table
# ---------------------------------------------------------------------------


class TestChurnCalibrationModelsTable:
    def test_churn_calibration_models_table(self, migrated_engine):
        """
        churn_calibration_models must exist with all required columns per PRD §3.1.
        organization_id nullable (NULL = global fallback model).
        A partial index on is_active must exist.
        """
        insp = inspect(migrated_engine)
        assert insp.has_table("churn_calibration_models"), (
            "Table 'churn_calibration_models' does not exist."
        )

        cols = {
            c["name"] for c in insp.get_columns("churn_calibration_models")
        }
        required = {
            "id",
            "organization_id",
            "model_json",
            "label_count",
            "positive_count",
            "precision",
            "recall",
            "f1",
            "auc",
            "threshold_bands",
            "fit_at",
            "is_active",
        }
        missing = required - cols
        assert not missing, (
            f"Missing columns in churn_calibration_models: {missing}"
        )

        col_map = {
            c["name"]: c
            for c in insp.get_columns("churn_calibration_models")
        }
        assert col_map["organization_id"]["nullable"], (
            "organization_id must be nullable in churn_calibration_models"
        )

        idx_names = {
            i["name"] for i in insp.get_indexes("churn_calibration_models")
        }
        assert "ix_churn_cal_model_org_fit" in idx_names, (
            f"ix_churn_cal_model_org_fit not found in: {idx_names}"
        )
        assert "uq_churn_cal_model_one_active_per_org" in idx_names, (
            f"uq_churn_cal_model_one_active_per_org partial index not found: {idx_names}"
        )


# ---------------------------------------------------------------------------
# Test 5: churn_backtest_runs table
# ---------------------------------------------------------------------------


class TestChurnBacktestRunsTable:
    def test_churn_backtest_runs_table(self, migrated_engine):
        """
        churn_backtest_runs must exist with all required columns per PRD §3.1.
        organization_id nullable (NULL = global).
        Index ix_churn_backtest_org_run_at must exist.
        """
        insp = inspect(migrated_engine)
        assert insp.has_table("churn_backtest_runs"), (
            "Table 'churn_backtest_runs' does not exist."
        )

        cols = {c["name"] for c in insp.get_columns("churn_backtest_runs")}
        required = {
            "id",
            "organization_id",
            "calibration_model_id",
            "run_at",
            "label_count",
            "precision",
            "recall",
            "f1",
            "auc",
            "optimal_threshold",
            "duration_ms",
            "notes",
        }
        missing = required - cols
        assert not missing, f"Missing columns in churn_backtest_runs: {missing}"

        col_map = {
            c["name"]: c for c in insp.get_columns("churn_backtest_runs")
        }
        assert col_map["organization_id"]["nullable"], (
            "organization_id must be nullable in churn_backtest_runs"
        )
        assert col_map["notes"]["nullable"], "notes must be nullable"
        assert col_map["duration_ms"]["nullable"], "duration_ms must be nullable"

        idx_names = {
            i["name"] for i in insp.get_indexes("churn_backtest_runs")
        }
        assert "ix_churn_backtest_org_run_at" in idx_names, (
            f"ix_churn_backtest_org_run_at not found in: {idx_names}"
        )


# ---------------------------------------------------------------------------
# Test 6: churn_playbooks — CHECK constraint and self-FK
# ---------------------------------------------------------------------------


class TestChurnPlaybooksTable:
    def test_churn_playbooks_table(self, migrated_engine):
        """
        churn_playbooks must exist with all required columns.
        """
        insp = inspect(migrated_engine)
        assert insp.has_table("churn_playbooks"), (
            "Table 'churn_playbooks' does not exist."
        )

        cols = {c["name"] for c in insp.get_columns("churn_playbooks")}
        required = {
            "id",
            "organization_id",
            "name",
            "description",
            "probability_min",
            "probability_max",
            "action_sequence",
            "is_template",
            "is_active",
            "source_template_id",
            "created_at",
            "updated_at",
        }
        missing = required - cols
        assert not missing, f"Missing columns in churn_playbooks: {missing}"

    def test_churn_playbooks_check_constraint(self, migrated_engine):
        """
        Inserting probability_min >= probability_max must raise IntegrityError
        (CHECK constraint ck_playbook_probability_range).
        SQLite 3.25+ enforces CHECK constraints.
        """
        with pytest.raises(Exception):
            with migrated_engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                conn.execute(
                    text(
                        "INSERT INTO churn_playbooks"
                        " (name, probability_min, probability_max,"
                        "  action_sequence, is_template, is_active,"
                        "  created_at, updated_at)"
                        " VALUES (:name, :mn, :mx, :seq, 0, 1,"
                        "  '2026-01-01', '2026-01-01')"
                    ),
                    {
                        "name": "Bad Playbook",
                        "mn": 0.80,
                        "mx": 0.50,  # violates probability_min < probability_max
                        "seq": "[]",
                    },
                )


# ---------------------------------------------------------------------------
# Test 7: churn_playbook_executions table
# ---------------------------------------------------------------------------


class TestChurnPlaybookExecutionsTable:
    def test_churn_playbook_executions_table(self, migrated_engine):
        """
        churn_playbook_executions must exist with full column set and three indexes.
        """
        insp = inspect(migrated_engine)
        assert insp.has_table("churn_playbook_executions"), (
            "Table 'churn_playbook_executions' does not exist."
        )

        cols = {
            c["name"] for c in insp.get_columns("churn_playbook_executions")
        }
        required = {
            "id",
            "playbook_id",
            "organization_id",
            "customer_email",
            "triggered_by",
            "triggered_by_user_id",
            "status",
            "action_log",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
        }
        missing = required - cols
        assert not missing, (
            f"Missing columns in churn_playbook_executions: {missing}"
        )

        idx_names = {
            i["name"] for i in insp.get_indexes("churn_playbook_executions")
        }
        assert "ix_playbook_exec_org_created" in idx_names, (
            f"ix_playbook_exec_org_created not found in: {idx_names}"
        )
        assert "ix_playbook_exec_playbook_created" in idx_names, (
            f"ix_playbook_exec_playbook_created not found in: {idx_names}"
        )
        assert "ix_playbook_exec_email_created" in idx_names, (
            f"ix_playbook_exec_email_created not found in: {idx_names}"
        )


# ---------------------------------------------------------------------------
# Test 8: new columns on customer_health_scores
# ---------------------------------------------------------------------------


class TestCustomerHealthScoresNewColumns:
    def test_customer_health_scores_new_columns(self, migrated_engine):
        """
        Seven new columns per PRD §3.2 must be present on customer_health_scores:
        churn_probability, churn_probability_low, churn_probability_high,
        time_to_churn_bucket, calibration_model_id, probability_computed_at,
        has_potential_winback.
        """
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("customer_health_scores")}
        new_cols = {
            "churn_probability",
            "churn_probability_low",
            "churn_probability_high",
            "time_to_churn_bucket",
            "calibration_model_id",
            "probability_computed_at",
            "has_potential_winback",
        }
        missing = new_cols - cols
        assert not missing, (
            f"Missing new columns on customer_health_scores: {missing}"
        )

    def test_customer_health_scores_new_column_nullability(self, migrated_engine):
        """
        has_potential_winback must be NOT NULL.
        All other six new columns must be nullable.
        """
        insp = inspect(migrated_engine)
        col_map = {
            c["name"]: c
            for c in insp.get_columns("customer_health_scores")
        }

        assert not col_map["has_potential_winback"]["nullable"], (
            "has_potential_winback must be NOT NULL"
        )
        for col in (
            "churn_probability",
            "churn_probability_low",
            "churn_probability_high",
            "time_to_churn_bucket",
            "calibration_model_id",
            "probability_computed_at",
        ):
            assert col_map[col]["nullable"], f"{col} must be nullable"


# ---------------------------------------------------------------------------
# Test 9: downgrade reverses all changes
# ---------------------------------------------------------------------------


class TestMigrationDowngrade:
    def test_migration_downgrade_reverses_all_changes(self):
        """
        After upgrade() then downgrade():
        - All 5 new tables are dropped.
        - All 7 new columns are removed from customer_health_scores.
        """
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        # Upgrade.
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        for table in (
            "customer_churn_events",
            "churn_calibration_models",
            "churn_backtest_runs",
            "churn_playbooks",
            "churn_playbook_executions",
        ):
            assert insp.has_table(table), f"'{table}' should exist after upgrade"

        # Downgrade.
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        for table in (
            "customer_churn_events",
            "churn_calibration_models",
            "churn_backtest_runs",
            "churn_playbooks",
            "churn_playbook_executions",
        ):
            assert not insp2.has_table(table), (
                f"Table '{table}' still exists after downgrade."
            )

        remaining = {
            c["name"] for c in insp2.get_columns("customer_health_scores")
        }
        dropped = {
            "churn_probability",
            "churn_probability_low",
            "churn_probability_high",
            "time_to_churn_bucket",
            "calibration_model_id",
            "probability_computed_at",
            "has_potential_winback",
        }
        still_present = dropped & remaining
        assert not still_present, (
            f"Columns still present after downgrade: {still_present}"
        )

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)


# ---------------------------------------------------------------------------
# Test 10: idempotency — existing data survives migration, backfill applies
# ---------------------------------------------------------------------------


class TestMigrationIdempotentOnExistingData:
    def test_migration_idempotent_on_existing_data(self):
        """
        Insert a customer_health_scores row BEFORE upgrade(). After upgrade():
        - has_potential_winback must be FALSE (backfill).
        - All other new columns must be NULL.
        """
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as c:
            c.execute(text("PRAGMA foreign_keys = OFF"))
            c.execute(
                text(
                    "INSERT INTO customer_health_scores"
                    " (organization_id, customer_email, health_score,"
                    "  churn_risk_component, sentiment_component,"
                    "  resolution_component, frequency_component,"
                    "  risk_level, confidence_level, confidence_score,"
                    "  is_archived, created_at, updated_at)"
                    " VALUES (10, 'bob@example.com', 60, 50, 50, 50, 50,"
                    "  'moderate', 'medium', 40, 0,"
                    "  '2025-06-01', '2025-06-01')"
                )
            )

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT has_potential_winback, churn_probability,"
                    " time_to_churn_bucket, calibration_model_id"
                    " FROM customer_health_scores"
                    " WHERE customer_email = 'bob@example.com'"
                )
            ).fetchone()

        assert row is not None, "Pre-existing row not found after migration."
        assert row[0] == 0 or row[0] is False, (
            f"has_potential_winback should be FALSE after backfill, got {row[0]}"
        )
        assert row[1] is None, f"churn_probability should be NULL, got {row[1]}"
        assert row[2] is None, (
            f"time_to_churn_bucket should be NULL, got {row[2]}"
        )
        assert row[3] is None, (
            f"calibration_model_id should be NULL, got {row[3]}"
        )

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
