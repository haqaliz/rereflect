"""
TDD migration test for Phase B of the usage-trend-churn-signal aspect
(rollup-rewindow-fix): `customer_usage.active_days_14d` (Integer, nullable,
no server_default, no backfill).

Strategy
--------
Mirrors tests/test_churn_prediction_migration.py's approach:

1. Build a *pre-migration* metadata object containing only the subset of
   tables that matter here — `organizations` (FK target) and
   `customer_usage` WITHOUT `active_days_14d`.

2. Create those tables against a fresh temp-file SQLite database.

3. Apply this migration's upgrade() / downgrade() directly via the Alembic
   Operations proxy.

4. Inspect the schema with sqlalchemy.inspect() to verify correctness, and
   round-trip actual rows to prove existing data is untouched (no backfill).

Revision target: ``241f650d7068`` (slug: add_active_days_14d_to_customer_usage)
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

_migration = importlib.import_module(
    "241f650d7068_add_active_days_14d_to_customer_usage"
)

# ---------------------------------------------------------------------------
# Pre-migration metadata
# Defines only the tables that existed BEFORE our migration: organizations
# (FK target) and customer_usage WITHOUT active_days_14d.
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

sa.Table(
    "organizations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
)

sa.Table(
    "customer_usage",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("customer_email", sa.String(255), nullable=False),
    sa.Column("last_active_at", sa.DateTime(), nullable=True),
    sa.Column("login_count_7d", sa.Integer(), nullable=True),
    sa.Column("login_count_30d", sa.Integer(), nullable=True),
    sa.Column("active_days_7d", sa.Integer(), nullable=True),
    sa.Column("active_days_30d", sa.Integer(), nullable=True),
    sa.Column("usage_score", sa.Integer(), nullable=False, server_default="50"),
    sa.Column("events_total", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("first_seen_at", sa.DateTime(), nullable=True),
    sa.UniqueConstraint(
        "organization_id", "customer_email", name="uq_customer_usage_org_email"
    ),
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
    """Fresh temp-file SQLite engine with the PRE-MIGRATION schema."""
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
# Test 1: column exists and is nullable after upgrade
# ---------------------------------------------------------------------------


class TestActiveDays14dColumn:
    def test_active_days_14d_column_exists(self, migrated_engine):
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("customer_usage")}
        assert "active_days_14d" in cols, (
            "Column 'active_days_14d' does not exist on customer_usage after migration."
        )

    def test_active_days_14d_is_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_usage")}
        assert col_map["active_days_14d"]["nullable"], (
            "active_days_14d must be nullable"
        )


# ---------------------------------------------------------------------------
# Test 2: no backfill — pre-existing rows stay NULL
# ---------------------------------------------------------------------------


class TestActiveDays14dNoBackfill:
    def test_existing_rows_stay_null_after_upgrade(self):
        """
        A row inserted BEFORE upgrade() must have active_days_14d == NULL
        after upgrade() — no server_default, no backfill. The column is
        populated later by the first daily recompute or the customer's
        next event, never by the migration itself.
        """
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (1, 'Acme')")
            )
            conn.execute(
                text(
                    "INSERT INTO customer_usage"
                    " (organization_id, customer_email, active_days_7d,"
                    "  active_days_30d, usage_score, events_total)"
                    " VALUES (1, 'alice@example.com', 6, 25, 70, 40)"
                )
            )

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT active_days_14d FROM customer_usage"
                    " WHERE customer_email = 'alice@example.com'"
                )
            ).fetchone()

        assert row is not None, "Pre-existing row not found after migration."
        assert row[0] is None, (
            f"active_days_14d should be NULL (no backfill), got {row[0]}"
        )

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)


# ---------------------------------------------------------------------------
# Test 3: downgrade drops the column
# ---------------------------------------------------------------------------


class TestActiveDays14dDowngrade:
    def test_downgrade_drops_active_days_14d(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        assert "active_days_14d" in {
            c["name"] for c in insp.get_columns("customer_usage")
        }, "active_days_14d should exist after upgrade"

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        assert "active_days_14d" not in {
            c["name"] for c in insp2.get_columns("customer_usage")
        }, "active_days_14d should be dropped after downgrade"

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
