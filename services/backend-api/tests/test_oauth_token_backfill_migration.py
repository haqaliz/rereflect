"""
TDD migration test for the oauth-tokens-encryption-at-rest backfill
(bug/oauth-tokens-stored-plaintext): `integrations.oauth_access_token`
(Text, nullable) plaintext rows are encrypted in place with Fernet using
`LLM_ENCRYPTION_KEY`.

Contract pinned by this test:

1. Missing `LLM_ENCRYPTION_KEY` at upgrade time -> RuntimeError with an
   actionable message (fail-closed — deliberately NOT the h1i2j3k4l5m6:148
   "store as-is" fallback, which silently left keys plaintext).
2. upgrade() encrypts plaintext rows in place and the ciphertext
   round-trips through Fernet.
3. Rows already starting with the Fernet prefix `gAAAAA` are skipped (no
   double-encrypt).
4. NULL / empty-string rows are untouched.
5. downgrade() best-effort decrypts back to plaintext; missing key or
   corrupt ciphertext is skipped without raising.

Revision target: c7d8e9f0a1b2 (encrypt_integration_oauth_tokens),
down_revision ``a9b8c7d6e5f4`` (verified live via `alembic heads`, not
assumed).

Mirrors tests/test_usage_history_trend_columns_migration.py's structure.
"""

import importlib
import os
import sys
import tempfile
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Import the migration module under test
# ---------------------------------------------------------------------------

VERSIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
)
if VERSIONS_DIR not in sys.path:
    sys.path.insert(0, VERSIONS_DIR)

_migration = importlib.import_module("c7d8e9f0a1b2_encrypt_integration_oauth_tokens")

# ---------------------------------------------------------------------------
# Pre-migration metadata — integrations table subset only
# ---------------------------------------------------------------------------

_TEST_KEY_STR = Fernet.generate_key().decode()
_TEST_KEY = _TEST_KEY_STR.encode()

_PLAINTEXT = "slack-xoxb-plaintext"
_ALREADY_FERNET_PLAIN = "already-encrypted"
_ALREADY_FERNET = Fernet(_TEST_KEY).encrypt(_ALREADY_FERNET_PLAIN.encode()).decode()

_pre_meta = sa.MetaData()

sa.Table(
    "integrations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("type", sa.String(50), nullable=True),
    sa.Column("oauth_access_token", sa.Text(), nullable=True),
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


def _seed_rows(engine):
    """Plaintext (1), NULL (2), empty-string (3), already-Fernet (4)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO integrations (id, type, oauth_access_token) VALUES "
                "(1, 'slack', :plaintext), "
                "(2, 'slack', NULL), "
                "(3, 'intercom', ''), "
                "(4, 'slack', :already)"
            ),
            {"plaintext": _PLAINTEXT, "already": _ALREADY_FERNET},
        )


def _token(conn, row_id):
    return conn.execute(
        text("SELECT oauth_access_token FROM integrations WHERE id = :id"),
        {"id": row_id},
    ).scalar()


@pytest.fixture
def migrated_engine():
    engine = _make_engine()
    _pre_meta.create_all(bind=engine)
    _seed_rows(engine)
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": _TEST_KEY_STR}, clear=True):
        with engine.begin() as conn:
            _apply_upgrade(conn)
    yield engine
    _pre_meta.drop_all(bind=engine)
    _dispose(engine)


# ---------------------------------------------------------------------------
# Test 1 (fail-closed): missing LLM_ENCRYPTION_KEY -> RuntimeError, rows
# untouched (never the h1i2j3k4l5m6:148 silent-plaintext fallback).
# ---------------------------------------------------------------------------


class TestUpgradeFailClosed:
    def test_missing_key_raises_runtime_error_and_leaves_rows_untouched(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)
        _seed_rows(engine)

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="LLM_ENCRYPTION_KEY is not set"):
                with engine.begin() as conn:
                    _apply_upgrade(conn)

        with engine.connect() as conn:
            assert _token(conn, 1) == _PLAINTEXT

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)


# ---------------------------------------------------------------------------
# Test 2 (upgrade): plaintext encrypted + round-trips; already-Fernet
# unchanged; NULL/empty untouched.
# ---------------------------------------------------------------------------


class TestUpgradeEncrypts:
    def test_plaintext_row_encrypted_and_round_trips(self, migrated_engine):
        with migrated_engine.connect() as conn:
            stored = _token(conn, 1)
        assert stored != _PLAINTEXT
        assert stored.startswith("gAAAAA")
        assert Fernet(_TEST_KEY).decrypt(stored.encode()).decode() == _PLAINTEXT

    def test_already_fernet_row_unchanged(self, migrated_engine):
        with migrated_engine.connect() as conn:
            assert _token(conn, 4) == _ALREADY_FERNET

    def test_null_and_empty_rows_untouched(self, migrated_engine):
        with migrated_engine.connect() as conn:
            assert _token(conn, 2) is None
            assert _token(conn, 3) == ""


# ---------------------------------------------------------------------------
# Test 3 (downgrade): best-effort decrypt back to plaintext; missing key or
# corrupt ciphertext skipped without raising.
# ---------------------------------------------------------------------------


class TestDowngradeRestoresPlaintext:
    def test_downgrade_decrypts_back_to_plaintext(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)
        _seed_rows(engine)

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": _TEST_KEY_STR}, clear=True):
            with engine.begin() as conn:
                _apply_upgrade(conn)
            with engine.begin() as conn:
                _apply_downgrade(conn)

        with engine.connect() as conn:
            assert _token(conn, 1) == _PLAINTEXT
            assert _token(conn, 4) == _ALREADY_FERNET_PLAIN
            assert _token(conn, 2) is None
            assert _token(conn, 3) == ""

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)

    def test_downgrade_without_key_skips_without_raising(self):
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)
        _seed_rows(engine)

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": _TEST_KEY_STR}, clear=True):
            with engine.begin() as conn:
                _apply_upgrade(conn)

        with patch.dict(os.environ, {}, clear=True):
            with engine.begin() as conn:
                _apply_downgrade(conn)

        with engine.connect() as conn:
            assert _token(conn, 1).startswith("gAAAAA")

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)

    def test_downgrade_skips_corrupt_ciphertext_without_raising(self):
        corrupt = "gAAAAA-not-real-ciphertext"
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO integrations (id, type, oauth_access_token) "
                    "VALUES (1, 'slack', :corrupt)"
                ),
                {"corrupt": corrupt},
            )

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": _TEST_KEY_STR}, clear=True):
            with engine.begin() as conn:
                _apply_downgrade(conn)

        with engine.connect() as conn:
            assert _token(conn, 1) == corrupt

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
