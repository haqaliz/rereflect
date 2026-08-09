"""
TDD migration test for the Linear webhook-secret encryption-at-rest
backfill (bug/linear-webhook-secret-plaintext):
`linear_integrations.webhook_secret` (String(255), plaintext) rows are
encrypted in place with Fernet using `LLM_ENCRYPTION_KEY`.

Contract pinned by this test:

1. Missing `LLM_ENCRYPTION_KEY` at upgrade time -> RuntimeError with an
   actionable message (fail-closed — never silently leave Linear webhook
   secrets in plaintext).
2. upgrade() encrypts plaintext rows in place and the ciphertext
   round-trips through Fernet.
3. Rows already starting with the Fernet prefix `gAAAAA` are skipped (no
   double-encrypt).
4. NULL / empty-string rows are untouched.
5. downgrade() best-effort decrypts back to plaintext; missing key or
   corrupt ciphertext is skipped without raising.

Revision target: d3a2c5b7e9f4 (encrypt_linear_webhook_secret),
down_revision ``c7d8e9f0a1b2`` (verified live via `alembic heads`, not
assumed).

Mirrors tests/test_oauth_token_backfill_migration.py's structure.
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

_migration = importlib.import_module("d3a2c5b7e9f4_encrypt_linear_webhook_secret")

# ---------------------------------------------------------------------------
# Pre-migration metadata — linear_integrations table subset only
# ---------------------------------------------------------------------------

_TEST_KEY_STR = Fernet.generate_key().decode()
_TEST_KEY = _TEST_KEY_STR.encode()

_PLAINTEXT = "lin_webhook_secret_plaintext"
_ALREADY_FERNET_PLAIN = "already-encrypted"
_ALREADY_FERNET = Fernet(_TEST_KEY).encrypt(_ALREADY_FERNET_PLAIN.encode()).decode()

_pre_meta = sa.MetaData()

sa.Table(
    "linear_integrations",
    _pre_meta,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("webhook_secret", sa.String(255), nullable=True),
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
                "INSERT INTO linear_integrations (id, webhook_secret) VALUES "
                "(1, :plaintext), "
                "(2, NULL), "
                "(3, ''), "
                "(4, :already)"
            ),
            {"plaintext": _PLAINTEXT, "already": _ALREADY_FERNET},
        )


def _secret(conn, row_id):
    return conn.execute(
        text("SELECT webhook_secret FROM linear_integrations WHERE id = :id"),
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
# untouched.
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
            assert _secret(conn, 1) == _PLAINTEXT

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)


# ---------------------------------------------------------------------------
# Test 2 (upgrade): plaintext encrypted + round-trips; already-Fernet
# unchanged; NULL/empty untouched.
# ---------------------------------------------------------------------------


class TestUpgradeEncrypts:
    def test_plaintext_row_encrypted_and_round_trips(self, migrated_engine):
        with migrated_engine.connect() as conn:
            stored = _secret(conn, 1)
        assert stored != _PLAINTEXT
        assert stored.startswith("gAAAAA")
        assert Fernet(_TEST_KEY).decrypt(stored.encode()).decode() == _PLAINTEXT

    def test_already_fernet_row_unchanged(self, migrated_engine):
        with migrated_engine.connect() as conn:
            assert _secret(conn, 4) == _ALREADY_FERNET

    def test_null_and_empty_rows_untouched(self, migrated_engine):
        with migrated_engine.connect() as conn:
            assert _secret(conn, 2) is None
            assert _secret(conn, 3) == ""


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
            assert _secret(conn, 1) == _PLAINTEXT
            assert _secret(conn, 4) == _ALREADY_FERNET_PLAIN
            assert _secret(conn, 2) is None
            assert _secret(conn, 3) == ""

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
            assert _secret(conn, 1).startswith("gAAAAA")

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)

    def test_downgrade_skips_corrupt_ciphertext_without_raising(self):
        corrupt = "gAAAAA-not-real-ciphertext"
        engine = _make_engine()
        _pre_meta.create_all(bind=engine)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO linear_integrations (id, webhook_secret) "
                    "VALUES (1, :corrupt)"
                ),
                {"corrupt": corrupt},
            )

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": _TEST_KEY_STR}, clear=True):
            with engine.begin() as conn:
                _apply_downgrade(conn)

        with engine.connect() as conn:
            assert _secret(conn, 1) == corrupt

        _pre_meta.drop_all(bind=engine)
        _dispose(engine)
