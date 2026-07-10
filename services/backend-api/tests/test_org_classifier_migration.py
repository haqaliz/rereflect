"""
TDD migration tests for M5.2 per-org-corrections-classifier — data-layer aspect.

Strategy
--------
We cannot run the full Alembic chain against SQLite (existing migrations use
PostgreSQL-specific DDL). Instead we:

1. Build a *pre-migration* metadata object containing only the subset of
   tables that existed before this migration (organizations + org_ai_config
   WITHOUT classifier_mode), WITHOUT the two new org_classifier_* tables.

2. Create those tables against a fresh temp-file SQLite database.

3. Apply our migration's upgrade() / downgrade() functions directly via the
   Alembic Operations proxy.

4. Inspect the schema with sqlalchemy.inspect() to verify correctness.

Revision target: ``v2w3x4y5z6a7`` (slug: add_org_classifier_tables).

NOTE: the data-layer plan originally specified revision id 'y4z5a6b7c8d9',
but that id collided with an unrelated, already-merged migration
(y4z5a6b7c8d9_add_embedding_provider_dim_to_mappings). Renamed to
'v2w3x4y5z6a7'; down_revision stays '6ad1dc4335f1' per the plan.
"""

import importlib
import os
import sys
import tempfile

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# Import the migration module under test
# ---------------------------------------------------------------------------

VERSIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)
if VERSIONS_DIR not in sys.path:
    sys.path.insert(0, VERSIONS_DIR)

_migration = importlib.import_module("v2w3x4y5z6a7_add_org_classifier_tables")

# ---------------------------------------------------------------------------
# Pre-migration metadata
# Defines only the tables that existed BEFORE our migration.
# Deliberately excludes org_classifier_models / org_classifier_eval_runs
# and the classifier_mode column on org_ai_config.
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

sa.Table(
    "organizations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
    sa.Column("plan", sa.String(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
)

sa.Table(
    "org_ai_config",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("default_provider", sa.String(20), nullable=False, server_default="openai"),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
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
    engine = _make_engine()
    _pre_meta.create_all(bind=engine)
    yield engine
    _pre_meta.drop_all(bind=engine)
    _dispose(engine)


@pytest.fixture
def migrated_engine(pre_migration_engine):
    with pre_migration_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        _apply_upgrade(conn)
    yield pre_migration_engine


# ---------------------------------------------------------------------------
# Test: static revision pointer
# ---------------------------------------------------------------------------


class TestMigrationRevisionPointer:
    def test_single_head_pointer(self):
        assert _migration.revision == "v2w3x4y5z6a7"
        assert _migration.down_revision == "6ad1dc4335f1"


# ---------------------------------------------------------------------------
# Test: org_classifier_models table
# ---------------------------------------------------------------------------


class TestOrgClassifierModelsTable:
    def test_upgrade_creates_org_classifier_models(self, migrated_engine):
        insp = inspect(migrated_engine)
        assert insp.has_table("org_classifier_models"), (
            "Table 'org_classifier_models' does not exist after migration."
        )

        cols = {c["name"] for c in insp.get_columns("org_classifier_models")}
        required = {
            "id",
            "organization_id",
            "classifier_type",
            "model_json",
            "label_count",
            "precision",
            "recall",
            "macro_f1",
            "accuracy",
            "fit_at",
            "is_active",
        }
        missing = required - cols
        assert not missing, f"Missing columns in org_classifier_models: {missing}"

        col_map = {c["name"]: c for c in insp.get_columns("org_classifier_models")}
        assert col_map["organization_id"]["nullable"], (
            "organization_id must be nullable in org_classifier_models"
        )


# ---------------------------------------------------------------------------
# Test: org_classifier_eval_runs table
# ---------------------------------------------------------------------------


class TestOrgClassifierEvalRunsTable:
    def test_upgrade_creates_eval_runs(self, migrated_engine):
        insp = inspect(migrated_engine)
        assert insp.has_table("org_classifier_eval_runs"), (
            "Table 'org_classifier_eval_runs' does not exist after migration."
        )

        cols = {c["name"] for c in insp.get_columns("org_classifier_eval_runs")}
        required = {
            "id",
            "organization_id",
            "classifier_model_id",
            "classifier_type",
            "incumbent_macro_f1",
            "challenger_macro_f1",
            "macro_f1_delta",
            "decision",
            "n",
            "duration_ms",
            "notes",
            "created_at",
        }
        missing = required - cols
        assert not missing, f"Missing columns in org_classifier_eval_runs: {missing}"


# ---------------------------------------------------------------------------
# Test: classifier_mode column on org_ai_config
# ---------------------------------------------------------------------------


class TestClassifierModeColumn:
    def test_classifier_mode_added_to_org_ai_config(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("org_ai_config")}
        assert "classifier_mode" in col_map, "classifier_mode column missing on org_ai_config"
        assert col_map["classifier_mode"]["nullable"], "classifier_mode must be nullable"


# ---------------------------------------------------------------------------
# Test: partial-unique index enforced after migration
# ---------------------------------------------------------------------------


class TestPartialUniqueEnforced:
    def test_partial_unique_enforced_after_migration(self, migrated_engine):
        base_row = {
            "organization_id": 999,
            "classifier_type": "sentiment",
            "model_json": '{"v": 1}',
            "label_count": 10,
            "fit_at": "2026-07-10 00:00:00",
            "is_active": 1,
        }
        insert_sql = text(
            "INSERT INTO org_classifier_models"
            " (organization_id, classifier_type, model_json, label_count, fit_at, is_active)"
            " VALUES (:organization_id, :classifier_type, :model_json, :label_count, :fit_at, :is_active)"
        )

        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(insert_sql, base_row)

        # Second active row, same (org, classifier_type) -> IntegrityError
        with pytest.raises(IntegrityError):
            with migrated_engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                conn.execute(insert_sql, base_row)

        # Different classifier_type -> OK
        other_type_row = dict(base_row, classifier_type="category")
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(insert_sql, other_type_row)


# ---------------------------------------------------------------------------
# Test: organization_id NULL allowed
# ---------------------------------------------------------------------------


class TestOrgIdNullAllowed:
    def test_org_id_null_allowed(self, migrated_engine):
        insert_sql = text(
            "INSERT INTO org_classifier_models"
            " (organization_id, classifier_type, model_json, label_count, fit_at, is_active)"
            " VALUES (NULL, :classifier_type, :model_json, :label_count, :fit_at, :is_active)"
        )
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(
                insert_sql,
                {
                    "classifier_type": "sentiment",
                    "model_json": '{"v": 1}',
                    "label_count": 100,
                    "fit_at": "2026-07-10 00:00:00",
                    "is_active": 0,
                },
            )


# ---------------------------------------------------------------------------
# Test: indexes exist
# ---------------------------------------------------------------------------


class TestIndexesExist:
    def test_indexes_exist(self, migrated_engine):
        insp = inspect(migrated_engine)

        model_idx = {i["name"] for i in insp.get_indexes("org_classifier_models")}
        assert "uq_org_classifier_one_active" in model_idx, model_idx
        assert "ix_org_classifier_model_org_type_fit" in model_idx, model_idx

        eval_idx = {i["name"] for i in insp.get_indexes("org_classifier_eval_runs")}
        assert "ix_org_classifier_eval_org_type_created" in eval_idx, eval_idx


# ---------------------------------------------------------------------------
# Test: downgrade removes everything
# ---------------------------------------------------------------------------


class TestMigrationDowngrade:
    def test_downgrade_removes_everything(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        assert insp.has_table("org_classifier_models")
        assert insp.has_table("org_classifier_eval_runs")

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        assert not insp2.has_table("org_classifier_models")
        assert not insp2.has_table("org_classifier_eval_runs")

        remaining_cols = {c["name"] for c in insp2.get_columns("org_ai_config")}
        assert "classifier_mode" not in remaining_cols

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
