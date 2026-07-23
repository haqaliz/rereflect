"""
TDD migration test for the config-and-migration aspect of
usage-decline-churn-labels: `org_ai_config.usage_churn_labels_mode`
(String(20), nullable, server_default 'off') and
`org_ai_config.usage_churn_label_config` (JSON, nullable).

Mirrors tests/test_usage_trend_fields_migration.py's approach:

1. Build a *pre-migration* metadata object containing only the subset of
   tables that matter here — `organizations` (FK target, unused directly but
   kept for parity with sibling tests) and `org_ai_config` WITHOUT the two
   new columns.

2. Create those tables against a fresh temp-file SQLite database.

3. Apply this migration's upgrade() / downgrade() directly via the Alembic
   Operations proxy.

4. Inspect the schema with sqlalchemy.inspect() to verify correctness, and
   round-trip actual rows to prove existing data gets the server_default
   (no explicit backfill needed) and downgrade cleanly removes both columns.

Revision target: down_revision resolved live via `alembic heads` (single
head at authoring time: ``a1c2d3e4f5a6``, add_trend_to_usage_history).
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

_migration = importlib.import_module("0a3382154c27_add_usage_churn_label_config")

# ---------------------------------------------------------------------------
# Pre-migration metadata — org_ai_config WITHOUT the two new columns.
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

sa.Table(
    "organizations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
)

sa.Table(
    "org_ai_config",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column(
        "organization_id",
        sa.Integer(),
        sa.ForeignKey("organizations.id"),
        unique=True,
        nullable=False,
    ),
    sa.Column("default_provider", sa.String(20), nullable=False, server_default="openai"),
    sa.Column("urgency_classifier_mode", sa.String(20), nullable=True, server_default="off"),
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
# Test 1: columns exist with correct nullability + server_default after
# upgrade
# ---------------------------------------------------------------------------


class TestUsageChurnLabelColumnsExist:
    def test_usage_churn_labels_mode_column_exists_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("org_ai_config")}
        assert "usage_churn_labels_mode" in col_map
        assert col_map["usage_churn_labels_mode"]["nullable"], (
            "usage_churn_labels_mode must be nullable"
        )

    def test_usage_churn_labels_mode_server_default_is_off(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("org_ai_config")}
        default = col_map["usage_churn_labels_mode"]["default"]
        assert default is not None
        assert "off" in default

    def test_usage_churn_label_config_column_exists_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("org_ai_config")}
        assert "usage_churn_label_config" in col_map
        assert col_map["usage_churn_label_config"]["nullable"], (
            "usage_churn_label_config must be nullable"
        )


# ---------------------------------------------------------------------------
# Test 2: existing rows get the server_default, not backfilled to something
# else, and new rows omitting the column also get the default.
# ---------------------------------------------------------------------------


class TestUsageChurnLabelsModeDefault:
    def test_existing_row_gets_server_default_after_upgrade(self):
        """
        A row inserted BEFORE upgrade() must read usage_churn_labels_mode ==
        'off' after upgrade() (SQLite applies the server_default to existing
        rows on ADD COLUMN), and usage_churn_label_config must be NULL (no
        backfill of a JSON value).
        """
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'Acme')"))
            conn.execute(
                text(
                    "INSERT INTO org_ai_config"
                    " (organization_id, default_provider, urgency_classifier_mode)"
                    " VALUES (1, 'openai', 'off')"
                )
            )

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT usage_churn_labels_mode, usage_churn_label_config"
                    " FROM org_ai_config WHERE organization_id = 1"
                )
            ).fetchone()

        assert row is not None
        assert row[0] == "off"
        assert row[1] is None

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)

    def test_new_row_omitting_columns_gets_default(self, migrated_engine):
        with migrated_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            conn.execute(text("INSERT INTO organizations (id, name) VALUES (1, 'Acme')"))
            conn.execute(
                text(
                    "INSERT INTO org_ai_config"
                    " (organization_id, default_provider, urgency_classifier_mode)"
                    " VALUES (1, 'openai', 'off')"
                )
            )

        with migrated_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT usage_churn_labels_mode, usage_churn_label_config"
                    " FROM org_ai_config WHERE organization_id = 1"
                )
            ).fetchone()

        assert row[0] == "off"
        assert row[1] is None


# ---------------------------------------------------------------------------
# Test 3: downgrade drops both columns (reverse order)
# ---------------------------------------------------------------------------


class TestUsageChurnLabelConfigDowngrade:
    def test_downgrade_drops_both_columns(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("org_ai_config")}
        assert "usage_churn_labels_mode" in cols
        assert "usage_churn_label_config" in cols

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        cols2 = {c["name"] for c in insp2.get_columns("org_ai_config")}
        assert "usage_churn_labels_mode" not in cols2
        assert "usage_churn_label_config" not in cols2

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
