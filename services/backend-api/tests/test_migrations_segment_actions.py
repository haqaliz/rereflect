"""
TDD migration tests — segment-actions PRD, aspect `customer-fields-model`.

Adds `tags` (JSON) and `cs_owner_user_id` (FK -> users.id, ON DELETE SET
NULL) to `customer_health_scores`, plus index `ix_customer_health_cs_owner`
on (organization_id, cs_owner_user_id).

Strategy mirrors tests/test_churn_prediction_migration.py: build a
pre-migration metadata subset (organizations, users,
customer_health_scores WITHOUT the two new columns), apply this
migration's upgrade()/downgrade() directly via the Alembic Operations
proxy against a temp-file SQLite database, then inspect the schema.

Revision target: ``a6b703d7a303`` (slug: add_tags_and_cs_owner_to_customer_health)
"""

import os
import tempfile

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

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
    "a6b703d7a303_add_tags_and_cs_owner_to_customer_health"
)

# ---------------------------------------------------------------------------
# Pre-migration metadata — tables as they existed BEFORE this migration.
# Deliberately excludes `tags` and `cs_owner_user_id`.
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
    "users",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("email", sa.String(), nullable=False),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id")),
    sa.Column("role", sa.String(), nullable=False, server_default="member"),
    sa.Column("password_hash", sa.String(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
)

sa.Table(
    "customer_health_scores",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("customer_email", sa.String(255), nullable=False),
    sa.Column("customer_name", sa.String(255), nullable=True),
    sa.Column("health_score", sa.Integer(), nullable=False, server_default="50"),
    sa.Column("risk_level", sa.String(20), server_default="unknown"),
    sa.Column("segment", sa.String(30), nullable=True),
    sa.Column("confidence_level", sa.String(20), server_default="low"),
    sa.Column("feedback_count", sa.Integer(), server_default="0"),
    sa.Column("is_archived", sa.Boolean(), server_default="0"),
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
# Test 1 — upgrade adds the two columns
# ---------------------------------------------------------------------------


class TestUpgradeAddsColumns:
    def test_tags_and_cs_owner_columns_exist(self, migrated_engine):
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("customer_health_scores")}
        assert "tags" in cols, "Missing 'tags' column after upgrade"
        assert "cs_owner_user_id" in cols, "Missing 'cs_owner_user_id' column after upgrade"

    def test_new_columns_are_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("customer_health_scores")}
        assert col_map["tags"]["nullable"] is True
        assert col_map["cs_owner_user_id"]["nullable"] is True


# ---------------------------------------------------------------------------
# Test 2 — index exists
# ---------------------------------------------------------------------------


class TestCsOwnerIndex:
    def test_ix_customer_health_cs_owner_exists(self, migrated_engine):
        insp = inspect(migrated_engine)
        idx_names = {i["name"] for i in insp.get_indexes("customer_health_scores")}
        assert "ix_customer_health_cs_owner" in idx_names, (
            f"ix_customer_health_cs_owner not found in: {idx_names}"
        )

    def test_index_covers_org_and_owner_columns(self, migrated_engine):
        insp = inspect(migrated_engine)
        indexes = {i["name"]: i for i in insp.get_indexes("customer_health_scores")}
        idx = indexes["ix_customer_health_cs_owner"]
        assert idx["column_names"] == ["organization_id", "cs_owner_user_id"]


# ---------------------------------------------------------------------------
# Test 3 — downgrade removes both columns + index (round-trip)
# ---------------------------------------------------------------------------


class TestDowngradeRoundTrip:
    def test_downgrade_removes_columns_and_index(self, migrated_engine):
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("customer_health_scores")}
        assert "tags" not in cols
        assert "cs_owner_user_id" not in cols

        idx_names = {i["name"] for i in insp.get_indexes("customer_health_scores")}
        assert "ix_customer_health_cs_owner" not in idx_names

    def test_upgrade_downgrade_upgrade_round_trips_cleanly(self, pre_migration_engine):
        """Full round-trip: upgrade -> downgrade -> upgrade must not error."""
        with pre_migration_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)
        with pre_migration_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)
        with pre_migration_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(pre_migration_engine)
        cols = {c["name"] for c in insp.get_columns("customer_health_scores")}
        assert "tags" in cols
        assert "cs_owner_user_id" in cols
