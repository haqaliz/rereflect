"""
TDD migration tests for per-org-urgency-classifier (urgency-classifier-head,
data-and-config aspect).

Same strategy as test_org_ai_config_category_mode_migration.py: build a
pre-migration SQLite schema (org_ai_config WITH classifier_mode AND
category_classifier_mode, WITHOUT urgency_classifier_mode — i.e. the state
right after 3e26b38cbd15), apply this migration's upgrade()/downgrade() via
the Alembic Operations proxy directly, and inspect with sqlalchemy.inspect().

Revision target: ``e6f7a8b9c0d1`` (slug: add_urgency_classifier_mode).
down_revision: ``3e26b38cbd15`` (confirmed single head via `alembic heads`
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

_migration = importlib.import_module("e6f7a8b9c0d1_add_urgency_classifier_mode")

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
    sa.Column("classifier_mode", sa.String(20), nullable=True, server_default="off"),
    sa.Column("category_classifier_mode", sa.String(20), nullable=True, server_default="off"),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
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


class TestMigrationRevisionPointer:
    def test_revision_and_down_revision(self):
        assert _migration.revision == "e6f7a8b9c0d1"
        assert _migration.down_revision == "3e26b38cbd15"


class TestUrgencyClassifierModeColumn:
    def test_column_added_after_upgrade(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("org_ai_config")}
        assert "urgency_classifier_mode" in col_map, "urgency_classifier_mode column missing"
        assert col_map["urgency_classifier_mode"]["nullable"], "must be nullable"

    def test_existing_sibling_columns_untouched(self, migrated_engine):
        """Byte-stability: this migration must not alter the sibling columns."""
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("org_ai_config")}
        assert "classifier_mode" in col_map
        assert col_map["classifier_mode"]["nullable"]
        assert "category_classifier_mode" in col_map
        assert col_map["category_classifier_mode"]["nullable"]

    def test_server_default_off(self, migrated_engine):
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text(
                "INSERT INTO organizations (id, name, plan, created_at) "
                "VALUES (1, 'Acme', 'free', '2026-07-14 00:00:00')"
            ))
            conn.execute(text(
                "INSERT INTO org_ai_config (organization_id, default_provider, created_at, updated_at) "
                "VALUES (1, 'openai', '2026-07-14 00:00:00', '2026-07-14 00:00:00')"
            ))
            row = conn.execute(text(
                "SELECT urgency_classifier_mode FROM org_ai_config WHERE organization_id = 1"
            )).fetchone()
        assert row[0] == "off"


class TestMigrationDowngrade:
    def test_downgrade_removes_column_only(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        assert "urgency_classifier_mode" in {c["name"] for c in insp.get_columns("org_ai_config")}

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        remaining = {c["name"] for c in insp2.get_columns("org_ai_config")}
        assert "urgency_classifier_mode" not in remaining
        assert "classifier_mode" in remaining, "downgrade must not remove the sentiment column"
        assert "category_classifier_mode" in remaining, "downgrade must not remove the category column"

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
