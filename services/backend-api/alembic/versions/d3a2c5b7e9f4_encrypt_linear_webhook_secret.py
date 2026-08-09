"""encrypt_linear_webhook_secret

Encrypts existing plaintext ``linear_integrations.webhook_secret`` rows in
place with Fernet.

Online-only: uses ``op.get_bind()`` and does not support offline/``--sql``
mode (repo-wide backfill convention).

Fail-closed by design (decision 2026-08-09): if ``LLM_ENCRYPTION_KEY`` is
unset at migration time, upgrade() raises ``RuntimeError`` with
generate-a-key instructions rather than silently leaving Linear webhook
secrets in plaintext — the same shape as the OAuth-token backfill
(``c7d8e9f0a1b2``).

Idempotent: rows whose value starts with the Fernet ciphertext prefix
``gAAAAA`` are filtered out, so rows written by the fixed runtime in the
same branch are never double-encrypted and re-runs are safe.

downgrade() is best-effort: decrypts ciphertext back to plaintext per row,
skipping rows when the key is missing or the value fails to decrypt.

Revision ID: d3a2c5b7e9f4
Revises: c7d8e9f0a1b2
Create Date: 2026-08-09 00:00:00.000000

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3a2c5b7e9f4'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "LLM_ENCRYPTION_KEY is not set; refusing to leave Linear webhook "
            "secrets in plaintext. Generate a Fernet key (e.g. python -c "
            "\"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"), set "
            "LLM_ENCRYPTION_KEY, and re-run `alembic upgrade head`."
        )
    from cryptography.fernet import Fernet
    fernet = Fernet(key.encode())
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, webhook_secret FROM linear_integrations "
            "WHERE webhook_secret IS NOT NULL AND webhook_secret != '' "
            "AND webhook_secret NOT LIKE 'gAAAAA%'"
        )
    ).fetchall()
    for row_id, secret in rows:
        conn.execute(
            sa.text("UPDATE linear_integrations SET webhook_secret = :enc WHERE id = :id"),
            {"enc": fernet.encrypt(secret.encode()).decode(), "id": row_id},
        )


def downgrade() -> None:
    from cryptography.fernet import Fernet, InvalidToken

    conn = op.get_bind()
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    fernet = Fernet(key.encode()) if key else None
    rows = conn.execute(
        sa.text(
            "SELECT id, webhook_secret FROM linear_integrations "
            "WHERE webhook_secret IS NOT NULL AND webhook_secret != ''"
        )
    ).fetchall()
    for row_id, secret in rows:
        if fernet is None or not secret.startswith("gAAAAA"):
            continue  # cannot decrypt without the key — best-effort by convention
        try:
            plain = fernet.decrypt(secret.encode()).decode()
        except (ValueError, InvalidToken):
            pass  # corrupt or foreign ciphertext — leave the row as-is
        else:
            conn.execute(
                sa.text("UPDATE linear_integrations SET webhook_secret = :plain WHERE id = :id"),
                {"plain": plain, "id": row_id},
            )
