"""
TDD migration test for Phase C of the trend-detection-and-health aspect:
`customer_usage.usage_trend_state` (String(30), NOT NULL, server_default
'insufficient_history') and `customer_usage.usage_trend_pct` (Float, nullable).

Mirrors tests/test_active_days_14d_migration.py's approach:

1. Build a *pre-migration* metadata object containing only the subset of
   tables that matter here — `organizations` (FK target) and
   `customer_usage` WITHOUT the two trend columns.

2. Create those tables against a fresh temp-file SQLite database.

3. Apply this migration's upgrade() / downgrade() directly via the Alembic
   Operations proxy.

4. Inspect the schema with sqlalchemy.inspect() to verify correctness, and
   round-trip actual rows to prove existing data gets the server_default
   (no explicit backfill needed) and downgrade cleanly removes both columns.

Revision target: ``a5b63dbbce9b`` (slug: add_usage_trend_fields),
down_revision ``4988b7bbd0b6`` (usage-history-snapshot, the live single head
at the time this aspect was authored).
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

_migration = importlib.import_module("a5b63dbbce9b_add_usage_trend_fields")

# ---------------------------------------------------------------------------
# Pre-migration metadata — customer_usage WITHOUT the two trend columns.
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
    sa.Column("active_days_7d", sa.Integer(), nullable=True),
    sa.Column("active_days_14d", sa.Integer(), nullable=True),
    sa.Column("active_days_30d", sa.Integer(), nullable=True),
    sa.Column("usage_score", sa.Integer(), nullable=False, server_default="50"),
    sa.Column("events_total", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("first_seen_at", sa.DateTime(), nullable=True),
    sa.UniqueConstraint(
        "organization_id", "customer_email", name="uq_customer_usage_org_email"
    ),
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
# Test 1: columns exist with correct nullability after upgrade
# ---------------------------------------------------------------------------


class TestUsageTrendColumnsExist:
    def test_usage_trend_state_column_exists_not_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_usage")}
        assert "usage_trend_state" in col_map
        assert not col_map["usage_trend_state"]["nullable"], (
            "usage_trend_state must be NOT NULL"
        )

    def test_usage_trend_pct_column_exists_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_usage")}
        assert "usage_trend_pct" in col_map
        assert col_map["usage_trend_pct"]["nullable"], "usage_trend_pct must be nullable"


# ---------------------------------------------------------------------------
# Test 2: existing rows get the server_default, not backfilled to something
# else, and new rows omitting the column also get the default.
# ---------------------------------------------------------------------------


class TestUsageTrendStateDefault:
    def test_existing_row_gets_server_default_after_upgrade(self):
        """
        A row inserted BEFORE upgrade() must read usage_trend_state ==
        'insufficient_history' after upgrade() (SQLite applies the
        server_default to existing rows on ADD COLUMN), and
        usage_trend_pct must be NULL (no backfill of a numeric value).
        """
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'Acme')"))
            conn.execute(
                text(
                    "INSERT INTO customer_usage"
                    " (organization_id, customer_email, active_days_14d, usage_score, events_total)"
                    " VALUES (1, 'alice@example.com', 6, 70, 40)"
                )
            )

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT usage_trend_state, usage_trend_pct FROM customer_usage"
                    " WHERE customer_email = 'alice@example.com'"
                )
            ).fetchone()

        assert row is not None
        assert row[0] == "insufficient_history"
        assert row[1] is None

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)

    def test_new_row_omitting_columns_gets_default(self, migrated_engine):
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'Acme')"))
            conn.execute(
                text(
                    "INSERT INTO customer_usage"
                    " (organization_id, customer_email, usage_score, events_total)"
                    " VALUES (1, 'bob@example.com', 50, 0)"
                )
            )

        with migrated_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT usage_trend_state, usage_trend_pct FROM customer_usage"
                    " WHERE customer_email = 'bob@example.com'"
                )
            ).fetchone()

        assert row[0] == "insufficient_history"
        assert row[1] is None


# ---------------------------------------------------------------------------
# Test 3: downgrade drops both columns
# ---------------------------------------------------------------------------


class TestUsageTrendFieldsDowngrade:
    def test_downgrade_drops_both_columns(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("customer_usage")}
        assert "usage_trend_state" in cols
        assert "usage_trend_pct" in cols

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        cols2 = {c["name"] for c in insp2.get_columns("customer_usage")}
        assert "usage_trend_state" not in cols2
        assert "usage_trend_pct" not in cols2

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
