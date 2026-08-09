"""encrypt_integration_oauth_tokens

Encrypts existing plaintext ``integrations.oauth_access_token`` rows in
place with Fernet.

Online-only: uses ``op.get_bind()`` and does not support offline/``--sql``
mode (repo-wide backfill convention).

Fail-closed by design (decision 2026-08-09): if ``LLM_ENCRYPTION_KEY`` is
unset at migration time, upgrade() raises ``RuntimeError`` with
generate-a-key instructions rather than silently leaving OAuth tokens in
plaintext — deliberately NOT the h1i2j3k4l5m6:148 "store as-is" fallback,
which silently left keys plaintext.

Idempotent: rows already starting with the Fernet ciphertext prefix
``gAAAAA`` are skipped, so rows written by the fixed runtime in the same
branch (backend commit 4081f4ae, worker commit 2b94bc41) are never
double-encrypted and re-runs are safe.

downgrade() is best-effort: decrypts ciphertext back to plaintext per row,
skipping rows when the key is missing or the value fails to decrypt.

Revision ID: c7d8e9f0a1b2
Revises: a9b8c7d6e5f4
Create Date: 2026-08-09 00:00:00.000000

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'a9b8c7d6e5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "LLM_ENCRYPTION_KEY is not set; refusing to leave OAuth tokens in "
            "plaintext. Generate a Fernet key (e.g. python -c \"from cryptography.fernet "
            "import Fernet; print(Fernet.generate_key().decode())\"), set "
            "LLM_ENCRYPTION_KEY, and re-run `alembic upgrade head`."
        )
    from cryptography.fernet import Fernet
    fernet = Fernet(key.encode())
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, oauth_access_token FROM integrations "
            "WHERE oauth_access_token IS NOT NULL AND oauth_access_token != ''"
        )
    ).fetchall()
    for row_id, token in rows:
        if token.startswith("gAAAAA"):
            continue  # already Fernet ciphertext — never double-encrypt
        conn.execute(
            sa.text("UPDATE integrations SET oauth_access_token = :enc WHERE id = :id"),
            {"enc": fernet.encrypt(token.encode()).decode(), "id": row_id},
        )


def downgrade() -> None:
    from cryptography.fernet import Fernet, InvalidToken

    conn = op.get_bind()
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    fernet = Fernet(key.encode()) if key else None
    rows = conn.execute(
        sa.text(
            "SELECT id, oauth_access_token FROM integrations "
            "WHERE oauth_access_token IS NOT NULL AND oauth_access_token != ''"
        )
    ).fetchall()
    for row_id, token in rows:
        if fernet is None or not token.startswith("gAAAAA"):
            continue  # cannot decrypt without the key — best-effort by convention
        try:
            plain = fernet.decrypt(token.encode()).decode()
        except (ValueError, InvalidToken):
            pass  # corrupt or foreign ciphertext — leave the row as-is
        else:
            conn.execute(
                sa.text("UPDATE integrations SET oauth_access_token = :plain WHERE id = :id"),
                {"plain": plain, "id": row_id},
            )
