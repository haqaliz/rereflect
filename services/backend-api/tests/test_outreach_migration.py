"""
TDD migration test for the outreach-core aspect: `outreach_opt_out` on
`customer_health_scores` + the `outreach_campaigns` and
`outreach_campaign_recipients` tables.

Strategy
--------
Mirrors tests/test_active_days_14d_migration.py's approach:

1. Build a *pre-migration* metadata object containing only the tables that
   matter here — `organizations`, `users` (FK targets) and
   `customer_health_scores` WITHOUT `outreach_opt_out`.
2. Create those tables against a fresh temp-file SQLite database.
3. Apply this migration's upgrade() / downgrade() directly via the Alembic
   Operations proxy.
4. Inspect the schema with sqlalchemy.inspect() to verify correctness, and
   round-trip upgrade -> downgrade -> upgrade.

Revision target: ``f6a7b8c9d0e1`` (slug: add_outreach_tables), chained to the
head ``d3a2c5b7e9f4`` (confirmed single head via `alembic heads`).
"""

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

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

_migration = importlib.import_module("f6a7b8c9d0e1_add_outreach_tables")

# ---------------------------------------------------------------------------
# Pre-migration metadata
# Defines only the tables that existed BEFORE our migration: organizations
# and users (FK targets) and customer_health_scores WITHOUT outreach_opt_out.
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

sa.Table(
    "organizations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
)

sa.Table(
    "users",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("email", sa.String(255), nullable=False),
)

sa.Table(
    "customer_health_scores",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("customer_email", sa.String(255), nullable=False),
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
# Test 1: outreach_opt_out column exists and is NOT NULL
# ---------------------------------------------------------------------------


class TestOutreachOptOutColumn:
    def test_column_exists(self, migrated_engine):
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("customer_health_scores")}
        assert "outreach_opt_out" in cols, (
            "Column 'outreach_opt_out' does not exist on customer_health_scores after migration."
        )

    def test_column_is_not_null_with_false_default(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_health_scores")}
        col = col_map["outreach_opt_out"]
        assert col["nullable"] is False, "outreach_opt_out must be NOT NULL"
        assert "false" in str(col["default"]).lower(), (
            f"outreach_opt_out must default to false, got {col['default']!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: both outreach tables exist with the exact column sets
# ---------------------------------------------------------------------------


class TestOutreachTables:
    def test_outreach_campaigns_columns(self, migrated_engine):
        insp = inspect(migrated_engine)
        assert "outreach_campaigns" in insp.get_table_names()
        cols = {c["name"] for c in insp.get_columns("outreach_campaigns")}
        assert cols == {
            "id",
            "organization_id",
            "created_by_user_id",
            "subject",
            "body",
            "recipient_count",
            "status",
            "created_at",
        }, f"unexpected outreach_campaigns column set: {cols}"

    def test_outreach_campaigns_fks(self, migrated_engine):
        insp = inspect(migrated_engine)
        fks = insp.get_foreign_keys("outreach_campaigns")
        by_col = {fk["constrained_columns"][0]: fk for fk in fks}
        assert by_col["organization_id"]["referred_table"] == "organizations"
        assert by_col["created_by_user_id"]["referred_table"] == "users"

    def test_outreach_campaigns_status_default_queued(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("outreach_campaigns")}
        assert "queued" in str(col_map["status"]["default"]).lower(), (
            f"outreach_campaigns.status must default to 'queued', got {col_map['status']['default']!r}"
        )

    def test_outreach_campaign_recipients_columns(self, migrated_engine):
        insp = inspect(migrated_engine)
        assert "outreach_campaign_recipients" in insp.get_table_names()
        cols = {c["name"] for c in insp.get_columns("outreach_campaign_recipients")}
        assert cols == {
            "id",
            "campaign_id",
            "customer_email",
            "status",
            "error",
            "created_at",
        }, f"unexpected outreach_campaign_recipients column set: {cols}"

    def test_recipient_campaign_fk_cascades(self, migrated_engine):
        insp = inspect(migrated_engine)
        fks = insp.get_foreign_keys("outreach_campaign_recipients")
        campaign_fk = next(
            fk for fk in fks if fk["constrained_columns"] == ["campaign_id"]
        )
        assert campaign_fk["referred_table"] == "outreach_campaigns"
        assert campaign_fk.get("options", {}).get("ondelete") == "CASCADE", (
            "outreach_campaign_recipients.campaign_id must CASCADE on delete"
        )

    def test_recipient_campaign_email_unique(self, migrated_engine):
        insp = inspect(migrated_engine)
        uniques = insp.get_unique_constraints("outreach_campaign_recipients")
        assert any(
            uq["column_names"] == ["campaign_id", "customer_email"]
            for uq in uniques
        ), "outreach_campaign_recipients must have a unique (campaign_id, customer_email) constraint"


# ---------------------------------------------------------------------------
# Test 3: downgrade drops the column + both tables
# ---------------------------------------------------------------------------


class TestOutreachMigrationDowngrade:
    def test_downgrade_removes_everything(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        assert "outreach_campaigns" in insp.get_table_names()
        assert "outreach_campaign_recipients" in insp.get_table_names()

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        assert "outreach_campaigns" not in insp2.get_table_names()
        assert "outreach_campaign_recipients" not in insp2.get_table_names()
        assert "outreach_opt_out" not in {
            c["name"] for c in insp2.get_columns("customer_health_scores")
        }

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)


# ---------------------------------------------------------------------------
# Test 4: upgrade -> downgrade -> upgrade round-trips cleanly
# ---------------------------------------------------------------------------


class TestOutreachMigrationRoundTrip:
    def test_round_trip_recreates_schema(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        assert "outreach_campaigns" in insp.get_table_names()
        assert "outreach_campaign_recipients" in insp.get_table_names()
        assert "outreach_opt_out" in {
            c["name"] for c in insp.get_columns("customer_health_scores")
        }

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)


# ---------------------------------------------------------------------------
# Test 5: alembic heads prints exactly one head, chained to ours
# ---------------------------------------------------------------------------


class TestAlembicSingleHead:
    def test_alembic_heads_prints_one_head(self):
        backend_root = Path(__file__).resolve().parents[1]
        binary = backend_root / "venv" / "bin" / "alembic"
        if not binary.exists():
            binary = Path(shutil.which("alembic") or "/nonexistent")

        result = subprocess.run(
            [str(binary), "heads"],
            cwd=str(backend_root),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"alembic heads failed: {result.stderr}"
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        assert len(lines) == 1, (
            f"expected exactly one alembic head, got {len(lines)}: {lines}"
        )
        # The head moves with every new migration; update this pin when you add
        # one (currently 0bf182dad44d — playbook_tasks_table).
        assert "0bf182dad44d" in lines[0], (
            f"the single head must be the newest revision 0bf182dad44d, got: {lines[0]}"
        )
