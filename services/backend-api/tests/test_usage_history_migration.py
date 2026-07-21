"""
TDD migration test for the usage-history-snapshot aspect:
``customer_usage_history`` table (create + drop).

Mirrors tests/test_active_days_14d_migration.py's approach:

1. Build a *pre-migration* metadata object containing only the subset of
   tables that matter here — ``organizations`` (FK target). The table under
   test does not exist yet.

2. Create that table against a fresh temp-file SQLite database.

3. Apply this migration's upgrade() / downgrade() directly via the Alembic
   Operations proxy.

4. Inspect the schema with sqlalchemy.inspect() to verify correctness.

Revision target: ``4988b7bbd0b6`` (slug: add_customer_usage_history),
down_revision ``241f650d7068`` (rollup-rewindow-fix, the live single head at
the time this aspect was authored).
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

# ---------------------------------------------------------------------------
# Import the migration module under test
# ---------------------------------------------------------------------------

VERSIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)
if VERSIONS_DIR not in sys.path:
    sys.path.insert(0, VERSIONS_DIR)

_migration = importlib.import_module("4988b7bbd0b6_add_customer_usage_history")

# ---------------------------------------------------------------------------
# Pre-migration metadata — only organizations exists (FK target).
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

sa.Table(
    "organizations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
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


# ---------------------------------------------------------------------------
# Test 1: table + columns exist after upgrade
# ---------------------------------------------------------------------------


class TestCustomerUsageHistoryTable:
    def test_table_exists(self, migrated_engine):
        insp = inspect(migrated_engine)
        assert "customer_usage_history" in insp.get_table_names()

    def test_columns_exist(self, migrated_engine):
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("customer_usage_history")}
        expected = {
            "id",
            "organization_id",
            "customer_email",
            "snapshot_date",
            "active_days_7d",
            "active_days_14d",
            "active_days_30d",
            "login_count_30d",
            "distinct_feature_count",
            "usage_score",
            "last_active_at",
            "created_at",
        }
        assert expected <= cols, f"Missing columns: {expected - cols}"

    def test_payload_columns_are_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_usage_history")}
        for col_name in (
            "active_days_7d",
            "active_days_14d",
            "active_days_30d",
            "login_count_30d",
            "distinct_feature_count",
            "usage_score",
            "last_active_at",
        ):
            assert col_map[col_name]["nullable"], f"{col_name} must be nullable"

    def test_organization_id_and_customer_email_and_snapshot_date_not_nullable(
        self, migrated_engine
    ):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_usage_history")}
        for col_name in ("organization_id", "customer_email", "snapshot_date"):
            assert not col_map[col_name]["nullable"], f"{col_name} must be NOT NULL"


# ---------------------------------------------------------------------------
# Test 2: unique constraint (org, email, snapshot_date)
# ---------------------------------------------------------------------------


class TestCustomerUsageHistoryUniqueConstraint:
    def test_duplicate_org_email_date_raises_integrity_error(self, migrated_engine):
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'Acme')"))

        insert_sql = text(
            "INSERT INTO customer_usage_history"
            " (organization_id, customer_email, snapshot_date)"
            " VALUES (1, 'alice@example.com', '2026-07-22')"
        )
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(insert_sql)

        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            with migrated_engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                conn.execute(insert_sql)


# ---------------------------------------------------------------------------
# Test 3: composite lookback index exists (AC 8, structural)
# ---------------------------------------------------------------------------


class TestCustomerUsageHistoryIndexes:
    def test_lookback_index_exists_on_org_email_date(self, migrated_engine):
        insp = inspect(migrated_engine)
        indexes = insp.get_indexes("customer_usage_history")
        matching = [
            ix for ix in indexes
            if ix["column_names"] == ["organization_id", "customer_email", "snapshot_date"]
        ]
        assert matching, f"No composite index on (organization_id, customer_email, snapshot_date); got {indexes}"


# ---------------------------------------------------------------------------
# Test 4: downgrade drops the table
# ---------------------------------------------------------------------------


class TestCustomerUsageHistoryDowngrade:
    def test_downgrade_drops_table(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        assert "customer_usage_history" in insp.get_table_names()

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        assert "customer_usage_history" not in insp2.get_table_names()

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
