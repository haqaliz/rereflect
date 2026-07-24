"""
TDD migration tests for the staleness-model-key aspect (local-embedding-quality, M5.4).

Adds embedding_model (String(100), nullable) to query_template_mappings and
reworks the covering index from ix_mappings_provider_dim (provider, dimension)
to ix_mappings_provider_dim_model (provider, dimension, model).

Strategy mirrors test_churn_backfill_migration.py: build a pre-migration
metadata subset (query_template_mappings WITHOUT the new column, WITH the old
two-column index), apply upgrade()/downgrade() directly via the Alembic
Operations proxy against a temp-file SQLite engine, then inspect with
sqlalchemy.inspect().

Revision target: single head verified LIVE via `alembic heads` immediately
before authoring (non-negotiable per plan) -> 0a3382154c27. This migration's
down_revision = "0a3382154c27".
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

MIGRATION_MODULE = "hbsh5o3gbwv4_add_embedding_model_to_mappings"

_migration = importlib.import_module(MIGRATION_MODULE)


# ---------------------------------------------------------------------------
# Pre-migration metadata: query_template_mappings WITHOUT embedding_model,
# WITH the old ix_mappings_provider_dim index (mirrors the schema produced by
# y4z5a6b7c8d9, the migration this one revises).
# ---------------------------------------------------------------------------

_pre_meta = sa.MetaData()

_pre_mappings = sa.Table(
    "query_template_mappings",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("template_id", sa.Integer(), nullable=False),
    sa.Column("question_pattern", sa.Text(), nullable=False),
    sa.Column("question_embedding", sa.JSON(), nullable=True),
    sa.Column("embedding_provider", sa.String(50), nullable=True),
    sa.Column("embedding_dimension", sa.Integer(), nullable=True),
    sa.Column("match_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Index("ix_mappings_provider_dim", "embedding_provider", "embedding_dimension"),
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
    _dispose(engine)


@pytest.fixture
def migrated_engine(pre_migration_engine):
    with pre_migration_engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        _apply_upgrade(conn)
    yield pre_migration_engine


class TestRevisionChain:
    def test_down_revision_is_the_live_verified_head(self):
        assert _migration.down_revision == "0a3382154c27"

    def test_revision_id_is_new_and_unique(self):
        assert _migration.revision == "hbsh5o3gbwv4"
        assert _migration.revision != _migration.down_revision


class TestNewColumn:
    def test_embedding_model_column_present(self, migrated_engine):
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("query_template_mappings")}
        assert "embedding_model" in cols

    def test_embedding_model_column_nullable(self, migrated_engine):
        insp = inspect(migrated_engine)
        col_map = {c["name"]: c for c in insp.get_columns("query_template_mappings")}
        assert col_map["embedding_model"]["nullable"] is True


class TestIndexRework:
    def test_old_index_removed(self, migrated_engine):
        insp = inspect(migrated_engine)
        idx_names = {i["name"] for i in insp.get_indexes("query_template_mappings")}
        assert "ix_mappings_provider_dim" not in idx_names

    def test_new_model_aware_index_created(self, migrated_engine):
        insp = inspect(migrated_engine)
        indexes = {i["name"]: i for i in insp.get_indexes("query_template_mappings")}
        assert "ix_mappings_provider_dim_model" in indexes
        assert indexes["ix_mappings_provider_dim_model"]["column_names"] == [
            "embedding_provider",
            "embedding_dimension",
            "embedding_model",
        ]


class TestBackfill:
    def test_openai_1536_row_backfills_to_text_embedding_3_small(self, pre_migration_engine):
        with pre_migration_engine.begin() as c:
            c.execute(text("PRAGMA foreign_keys = OFF"))
            c.execute(
                text(
                    "INSERT INTO query_template_mappings"
                    " (template_id, question_pattern, embedding_provider,"
                    "  embedding_dimension, match_count, created_at)"
                    " VALUES (1, 'q1', 'openai', 1536, 0, '2026-01-01')"
                )
            )

        with pre_migration_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with pre_migration_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT embedding_model FROM query_template_mappings"
                    " WHERE question_pattern = 'q1'"
                )
            ).fetchone()

        assert row is not None
        assert row[0] == "text-embedding-3-small"

    def test_null_provider_row_stays_null(self, pre_migration_engine):
        with pre_migration_engine.begin() as c:
            c.execute(text("PRAGMA foreign_keys = OFF"))
            c.execute(
                text(
                    "INSERT INTO query_template_mappings"
                    " (template_id, question_pattern, match_count, created_at)"
                    " VALUES (2, 'q2', 0, '2026-01-01')"
                )
            )

        with pre_migration_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with pre_migration_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT embedding_model FROM query_template_mappings"
                    " WHERE question_pattern = 'q2'"
                )
            ).fetchone()

        assert row is not None
        assert row[0] is None

    def test_non_openai_provider_stays_null(self, pre_migration_engine):
        with pre_migration_engine.begin() as c:
            c.execute(text("PRAGMA foreign_keys = OFF"))
            c.execute(
                text(
                    "INSERT INTO query_template_mappings"
                    " (template_id, question_pattern, embedding_provider,"
                    "  embedding_dimension, match_count, created_at)"
                    " VALUES (3, 'q3', 'openai_compatible', 768, 0, '2026-01-01')"
                )
            )

        with pre_migration_engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        with pre_migration_engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT embedding_model FROM query_template_mappings"
                    " WHERE question_pattern = 'q3'"
                )
            ).fetchone()

        assert row is not None
        assert row[0] is None


class TestMigrationDowngrade:
    def test_downgrade_removes_column_and_restores_old_index(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_upgrade(conn)

        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("query_template_mappings")}
        assert "embedding_model" in cols
        idx_names = {i["name"] for i in insp.get_indexes("query_template_mappings")}
        assert "ix_mappings_provider_dim_model" in idx_names

        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            _apply_downgrade(conn)

        insp2 = inspect(engine)
        cols2 = {c["name"] for c in insp2.get_columns("query_template_mappings")}
        assert "embedding_model" not in cols2
        idx_names2 = {i["name"] for i in insp2.get_indexes("query_template_mappings")}
        assert "ix_mappings_provider_dim_model" not in idx_names2
        assert "ix_mappings_provider_dim" in idx_names2

        _dispose(engine)


class TestModelColumn:
    """Verify the ORM model has the new column and updated index."""

    def test_model_has_embedding_model_column(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping()
        assert hasattr(mapping, "embedding_model")

    def test_embedding_model_defaults_none(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping()
        assert mapping.embedding_model is None

    def test_can_set_embedding_model(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping(embedding_model="text-embedding-3-small")
        assert mapping.embedding_model == "text-embedding-3-small"

    def test_table_args_index_is_model_aware(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        index_names = {ix.name for ix in QueryTemplateMapping.__table__.indexes}
        assert "ix_mappings_provider_dim_model" in index_names
        assert "ix_mappings_provider_dim" not in index_names

        idx = next(
            ix for ix in QueryTemplateMapping.__table__.indexes
            if ix.name == "ix_mappings_provider_dim_model"
        )
        col_names = [c.name for c in idx.columns]
        assert col_names == ["embedding_provider", "embedding_dimension", "embedding_model"]
