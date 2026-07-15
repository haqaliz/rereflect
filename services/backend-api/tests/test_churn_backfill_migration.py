"""
TDD migration tests for the historical-backfill aspect (crm-churn-labels, M7).

Adds four backfill_* progress columns to BOTH hubspot_integrations and
salesforce_integrations: backfill_status, backfill_progress,
backfill_last_run_at, backfill_error. All nullable, no server_default
(NULL reads as "idle" at the application layer — house convention, mirrors
churn_event.py's status-as-Python-list-not-DB-CHECK precedent).

Strategy mirrors test_churn_prediction_migration.py: build a pre-migration
metadata subset (both integration tables WITHOUT the four new columns),
apply upgrade()/downgrade() directly via the Alembic Operations proxy
against a temp-file SQLite engine, then inspect with sqlalchemy.inspect().

Revision target: single head verified LIVE via `alembic heads` immediately
before authoring (non-negotiable per plan) -> f7a8b9c0d1e2. This migration's
down_revision = "f7a8b9c0d1e2".
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

VERSIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)
if VERSIONS_DIR not in sys.path:
    sys.path.insert(0, VERSIONS_DIR)

MIGRATION_MODULE = "b8c9d0e1f2a3_add_churn_backfill_progress_columns"

_migration = importlib.import_module(MIGRATION_MODULE)


# ---------------------------------------------------------------------------
# Pre-migration metadata: both integration tables WITHOUT the four new
# backfill_* columns.
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

sa.Table(
    "hubspot_integrations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), nullable=False),
    sa.Column("access_token", sa.Text(), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
    sa.Column("churn_labels_enabled", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("churn_label_config", sa.JSON(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
)

sa.Table(
    "salesforce_integrations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), nullable=False),
    sa.Column("refresh_token", sa.Text(), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
    sa.Column("churn_labels_enabled", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("churn_label_config", sa.JSON(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
)


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


NEW_COLUMNS = {
    "backfill_status",
    "backfill_progress",
    "backfill_last_run_at",
    "backfill_error",
}


class TestRevisionChain:
    def test_down_revision_is_the_live_verified_head(self):
        assert _migration.down_revision == "f7a8b9c0d1e2"


class TestHubSpotIntegrationsNewColumns:
    def test_new_columns_present(self, migrated_engine):
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("hubspot_integrations")}
        missing = NEW_COLUMNS - cols
        assert not missing, f"Missing columns on hubspot_integrations: {missing}"

    def test_new_columns_all_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("hubspot_integrations")}
        for col in NEW_COLUMNS:
            assert col_map[col]["nullable"], f"{col} must be nullable"


class TestSalesforceIntegrationsNewColumns:
    def test_new_columns_present(self, migrated_engine):
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("salesforce_integrations")}
        missing = NEW_COLUMNS - cols
        assert not missing, f"Missing columns on salesforce_integrations: {missing}"

    def test_new_columns_all_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("salesforce_integrations")}
        for col in NEW_COLUMNS:
            assert col_map[col]["nullable"], f"{col} must be nullable"


class TestNoServerDefault:
    def test_existing_row_reads_null_not_idle(self, pre_migration_engine):
        """
        NULL reads as 'idle' at the application layer (house convention) —
        the migration itself must NOT inject a server_default of 'idle',
        so a pre-existing row stays NULL after upgrade (no silent rewrite).
        """
        with pre_migration_engine.begin() as c:
            c.execute(text("PRAGMA foreign_keys = OFF"))
            c.execute(
                text(
                    "INSERT INTO hubspot_integrations"
                    " (organization_id, access_token, is_active,"
                    "  churn_labels_enabled, created_at, updated_at)"
                    " VALUES (1, 'enc', 1, 1, '2026-01-01', '2026-01-01')"
                )
            )

        with pre_migration_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with pre_migration_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT backfill_status, backfill_progress,"
                    " backfill_last_run_at, backfill_error"
                    " FROM hubspot_integrations WHERE organization_id = 1"
                )
            ).fetchone()

        assert row is not None
        assert row[0] is None
        assert row[1] is None
        assert row[2] is None
        assert row[3] is None


class TestMigrationDowngrade:
    def test_downgrade_removes_all_four_columns_from_both_tables(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        for table in ("hubspot_integrations", "salesforce_integrations"):
            cols = {c["name"] for c in insp.get_columns(table)}
            assert NEW_COLUMNS <= cols, f"upgrade() did not add all columns to {table}"

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        for table in ("hubspot_integrations", "salesforce_integrations"):
            cols = {c["name"] for c in insp2.get_columns(table)}
            still_present = NEW_COLUMNS & cols
            assert not still_present, (
                f"Columns still present on {table} after downgrade: {still_present}"
            )

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
