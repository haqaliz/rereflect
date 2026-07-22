"""
TDD migration test for the snapshot-trend-columns aspect
(usage-trend-automation-trigger, M3):
`customer_usage_history.usage_trend_state` (String(30), nullable, NO
server_default) and `customer_usage_history.usage_trend_pct` (Float,
nullable, NO server_default).

Mirrors tests/test_usage_trend_fields_migration.py's approach (the
customer_usage sibling), except both new columns here are nullable with no
default — pre-existing snapshot rows genuinely have no known trend state,
and the downstream timeline-trend-event aspect relies on NULL meaning
"unknown, skip" rather than a real state.

1. Build a *pre-migration* metadata object containing only the subset of
   tables that matter here — `organizations` (FK target) and
   `customer_usage_history` WITHOUT the two trend columns.

2. Create those tables against a fresh temp-file SQLite database.

3. Apply this migration's upgrade() / downgrade() directly via the Alembic
   Operations proxy.

4. Inspect the schema with sqlalchemy.inspect() to verify correctness, and
   round-trip actual rows to prove a row inserted without either new column
   succeeds and reads back NULL, and downgrade cleanly removes both columns.

Revision target: TBD (add_trend_to_usage_history), down_revision
``a5b63dbbce9b`` (add_usage_trend_fields, the live single head at the time
this aspect was authored — verified live via `alembic heads`, not assumed).
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

_migration = importlib.import_module("a1c2d3e4f5a6_add_trend_to_usage_history")

# ---------------------------------------------------------------------------
# Pre-migration metadata — customer_usage_history WITHOUT the two trend
# columns.
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

sa.Table(
    "organizations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
)

sa.Table(
    "customer_usage_history",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("customer_email", sa.String(255), nullable=False),
    sa.Column("snapshot_date", sa.Date(), nullable=False),
    sa.Column("active_days_7d", sa.Integer(), nullable=True),
    sa.Column("active_days_14d", sa.Integer(), nullable=True),
    sa.Column("active_days_30d", sa.Integer(), nullable=True),
    sa.Column("login_count_30d", sa.Integer(), nullable=True),
    sa.Column("distinct_feature_count", sa.Integer(), nullable=True),
    sa.Column("usage_score", sa.Integer(), nullable=True),
    sa.Column("last_active_at", sa.DateTime(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.UniqueConstraint(
        "organization_id",
        "customer_email",
        "snapshot_date",
        name="uq_customer_usage_history_org_email_date",
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
# Test 1 (AC1): both columns exist and are nullable after upgrade
# ---------------------------------------------------------------------------


class TestUsageHistoryTrendColumnsExist:
    def test_usage_trend_state_column_exists_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_usage_history")}
        assert "usage_trend_state" in col_map
        assert col_map["usage_trend_state"]["nullable"], (
            "usage_trend_state must be nullable on customer_usage_history "
            "(unlike the customer_usage sibling, which is NOT NULL)"
        )

    def test_usage_trend_pct_column_exists_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_usage_history")}
        assert "usage_trend_pct" in col_map
        assert col_map["usage_trend_pct"]["nullable"], "usage_trend_pct must be nullable"


# ---------------------------------------------------------------------------
# Test 2 (AC1/AC5): a row written without either new column succeeds and
# reads back NULL — no server_default backfill happens (deliberately unlike
# customer_usage.usage_trend_state).
# ---------------------------------------------------------------------------


class TestUsageHistoryTrendColumnsNoDefault:
    def test_existing_row_stays_null_after_upgrade(self):
        """
        A row inserted BEFORE upgrade() must read both usage_trend_state and
        usage_trend_pct as NULL after upgrade() — there is no server_default,
        so pre-existing snapshot rows are left untouched (AC5).
        """
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'Acme')"))
            conn.execute(
                text(
                    "INSERT INTO customer_usage_history"
                    " (organization_id, customer_email, snapshot_date, usage_score, created_at)"
                    " VALUES (1, 'alice@example.com', '2026-07-20', 70, '2026-07-20 00:00:00')"
                )
            )

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT usage_trend_state, usage_trend_pct FROM customer_usage_history"
                    " WHERE customer_email = 'alice@example.com'"
                )
            ).fetchone()

        assert row is not None
        assert row[0] is None
        assert row[1] is None

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)

    def test_new_row_omitting_columns_succeeds_and_reads_null(self, migrated_engine):
        """A row written after upgrade() without the new columns succeeds and
        reads back NULL (AC1) — no server_default fills them in."""
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'Acme')"))
            conn.execute(
                text(
                    "INSERT INTO customer_usage_history"
                    " (organization_id, customer_email, snapshot_date, usage_score, created_at)"
                    " VALUES (1, 'bob@example.com', '2026-07-21', 50, '2026-07-21 00:00:00')"
                )
            )

        with migrated_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT usage_trend_state, usage_trend_pct FROM customer_usage_history"
                    " WHERE customer_email = 'bob@example.com'"
                )
            ).fetchone()

        assert row[0] is None
        assert row[1] is None


# ---------------------------------------------------------------------------
# Test 3 (AC5): upgrade() -> downgrade() round-trips cleanly, dropping both
# columns.
# ---------------------------------------------------------------------------


class TestUsageHistoryTrendColumnsDowngrade:
    def test_downgrade_drops_both_columns(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("customer_usage_history")}
        assert "usage_trend_state" in cols
        assert "usage_trend_pct" in cols

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        cols2 = {c["name"] for c in insp2.get_columns("customer_usage_history")}
        assert "usage_trend_state" not in cols2
        assert "usage_trend_pct" not in cols2

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
