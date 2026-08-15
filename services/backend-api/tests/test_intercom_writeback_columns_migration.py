"""
TDD migration tests for intercom-writeback (db-config-model aspect, R1 + R4).

Same strategy as test_org_ai_config_churn_mode_migration.py: build a
pre-migration SQLite schema (intercom_integrations and feedback_items WITH the
pre-existing columns, WITHOUT the writeback columns — i.e. the state right
after 8114adde5d96 + 3cb9a0d1456b), apply this migration's upgrade()/downgrade()
via the Alembic Operations proxy directly, and inspect with
sqlalchemy.inspect().

Revision target: ``e4f5a6b7c8d9`` (slug: add_intercom_writeback_columns).
down_revision: ``3cb9a0d1456b`` (confirmed single head via `alembic heads`
at authoring time).
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

VERSIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)
if VERSIONS_DIR not in sys.path:
    sys.path.insert(0, VERSIONS_DIR)

_migration = importlib.import_module("e4f5a6b7c8d9_add_intercom_writeback_columns")

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
    "intercom_integrations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("access_token", sa.Text(), nullable=False),
    sa.Column("client_secret", sa.Text(), nullable=True),
    sa.Column("token_hint", sa.String(8), nullable=True),
    sa.Column("workspace_id", sa.String(255), nullable=False),
    sa.Column("workspace_name", sa.String(255), nullable=True),
    sa.Column("admin_id", sa.String(255), nullable=True),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("connected_by_user_id", sa.Integer(), nullable=True),
    sa.Column("connected_at", sa.DateTime(), nullable=False),
    sa.Column("last_synced_at", sa.DateTime(), nullable=True),
    sa.Column("last_sync_status", sa.String(50), nullable=True),
    sa.Column("last_error", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
)

sa.Table(
    "feedback_items",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("organization_id", sa.Integer(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("source", sa.String(), nullable=True),
    sa.Column("workflow_status", sa.String(50), nullable=False, server_default="new"),
    sa.Column("created_at", sa.DateTime(), nullable=False),
)


def _make_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
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


NEW_INTEGRATION_COLUMNS = (
    "writeback_enabled",
    "writeback_action",
    "last_writeback_at",
    "last_writeback_status",
    "last_writeback_error",
)
NEW_FEEDBACK_COLUMNS = ("intercom_writeback_at",)
ALL_NEW_COLUMNS = NEW_INTEGRATION_COLUMNS + NEW_FEEDBACK_COLUMNS

SIBLING_INTEGRATION_COLUMNS = (
    "is_active",
    "workspace_id",
    "last_synced_at",
    "last_error",
    "created_at",
    "updated_at",
)
SIBLING_FEEDBACK_COLUMNS = ("workflow_status", "created_at")


class TestMigrationRevisionPointer:
    def test_revision_and_down_revision(self):
        assert _migration.revision == "e4f5a6b7c8d9"
        assert _migration.down_revision == "3cb9a0d1456b"


class TestWritebackColumnsAdded:
    def test_five_columns_added_to_intercom_integrations(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("intercom_integrations")}
        for name in NEW_INTEGRATION_COLUMNS:
            assert name in col_map, f"intercom_integrations.{name} column missing"

    def test_marker_column_added_to_feedback_items(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("feedback_items")}
        assert "intercom_writeback_at" in col_map, "feedback_items.intercom_writeback_at missing"

    def test_required_columns_not_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        integ_cols = {c["name"]: c for c in insp.get_columns("intercom_integrations")}
        for name in ("writeback_enabled", "writeback_action"):
            assert integ_cols[name]["nullable"] is False, f"{name} must be NOT NULL"
        for name in ("last_writeback_at", "last_writeback_status", "last_writeback_error"):
            assert integ_cols[name]["nullable"] is True, f"{name} must be nullable"
        fb_cols = {c["name"]: c for c in insp.get_columns("feedback_items")}
        assert fb_cols["intercom_writeback_at"]["nullable"] is True

    def test_existing_columns_untouched(self, migrated_engine):
        insp = inspect(migrated_engine)
        integ_cols = {c["name"]: c for c in insp.get_columns("intercom_integrations")}
        fb_cols = {c["name"]: c for c in insp.get_columns("feedback_items")}
        for sibling in SIBLING_INTEGRATION_COLUMNS:
            assert sibling in integ_cols, f"sibling column {sibling} disappeared"
        for sibling in SIBLING_FEEDBACK_COLUMNS:
            assert sibling in fb_cols, f"sibling column {sibling} disappeared"


class TestServerDefaultsBackfill:
    def test_existing_rows_backfill_writeback_enabled_false(self, migrated_engine):
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text(
                "INSERT INTO organizations (id, name, plan, created_at) "
                "VALUES (1, 'Acme', 'free', '2026-07-14 00:00:00')"
            ))
            conn.execute(text(
                "INSERT INTO intercom_integrations "
                "(id, organization_id, access_token, workspace_id, is_active, "
                " connected_at, created_at, updated_at) "
                "VALUES (1, 1, 'enc:token', 'ws_acme', 1, "
                "        '2026-07-14 00:00:00', '2026-07-14 00:00:00', '2026-07-14 00:00:00')"
            ))
            row = conn.execute(text(
                "SELECT writeback_enabled FROM intercom_integrations WHERE id = 1"
            )).fetchone()
        # SQLite stores the boolean server_default as the literal text
        # "false"; Postgres returns a real bool False.
        assert row[0] in (False, 0, "false")

    def test_existing_rows_backfill_writeback_action_note_and_close(self, migrated_engine):
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text(
                "INSERT INTO organizations (id, name, plan, created_at) "
                "VALUES (1, 'Acme', 'free', '2026-07-14 00:00:00')"
            ))
            conn.execute(text(
                "INSERT INTO intercom_integrations "
                "(id, organization_id, access_token, workspace_id, is_active, "
                " connected_at, created_at, updated_at) "
                "VALUES (1, 1, 'enc:token', 'ws_acme', 1, "
                "        '2026-07-14 00:00:00', '2026-07-14 00:00:00', '2026-07-14 00:00:00')"
            ))
            row = conn.execute(text(
                "SELECT writeback_action FROM intercom_integrations WHERE id = 1"
            )).fetchone()
        assert row[0] == "note_and_close"

    def test_existing_feedback_rows_have_null_marker(self, migrated_engine):
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text(
                "INSERT INTO feedback_items (id, organization_id, text, created_at) "
                "VALUES (1, 1, 'hello', '2026-07-14 00:00:00')"
            ))
            row = conn.execute(text(
                "SELECT intercom_writeback_at FROM feedback_items WHERE id = 1"
            )).fetchone()
        assert row[0] is None


class TestMigrationDowngrade:
    def test_downgrade_drops_exactly_the_new_columns(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        after_upgrade = {c["name"] for c in insp.get_columns("intercom_integrations")} | {
            c["name"] for c in insp.get_columns("feedback_items")
        }
        for name in ALL_NEW_COLUMNS:
            assert name in after_upgrade

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        integ_remaining = {c["name"] for c in insp2.get_columns("intercom_integrations")}
        fb_remaining = {c["name"] for c in insp2.get_columns("feedback_items")}
        remaining = integ_remaining | fb_remaining
        for name in ALL_NEW_COLUMNS:
            assert name not in remaining, f"downgrade must drop {name}"
        for sibling in SIBLING_INTEGRATION_COLUMNS + SIBLING_FEEDBACK_COLUMNS:
            assert sibling in remaining, f"downgrade must not remove {sibling}"

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
