"""add asana_integrations.webhook_url_token (unguessable webhook URL)

Security fix (sec review, CRITICAL): the asana-webhook receiver previously
resolved the integration by a guessable integer path id
(`/inbound/{integration_id}`), and its handshake branch unconditionally
overwrote `integration.webhook_secret` on every request carrying an
`X-Hook-Secret` header -- together these let an unauthenticated attacker
POST a forged handshake to a small integer id, set a known secret for any
active org, and forge signed events afterward (cross-tenant status
tampering + DoS of the real webhook).

Adds `asana_integrations.webhook_url_token` (String(128), nullable) with a
UNIQUE index. This unguessable `secrets.token_urlsafe(32)` value is minted
by `POST /api/v1/integrations/asana/webhook/enable` and embedded in the
webhook target URL registered with Asana
(`{BACKEND_URL}/api/v1/webhooks/asana/inbound/{webhook_url_token}`); the
receiver (`src/api/routes/asana_webhook.py`) now resolves the integration by
this column instead of the integer id. NULL means the webhook has never
been enabled (fail-closed -- never matches any inbound path segment). This
migration is additive-only; existing rows get NULL and simply have no
working webhook until an operator re-runs POST /webhook/enable (which mints
a fresh token as part of the existing re-enable flow).

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`s2t3u4v5w6x7 (head)`. This revision chains directly off that sole verified
head -- no merge revision, no static parse.

Revision ID: t3u4v5w6x7y8
Revises: s2t3u4v5w6x7
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "t3u4v5w6x7y8"
down_revision = "s2t3u4v5w6x7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "asana_integrations", sa.Column("webhook_url_token", sa.String(length=128), nullable=True)
    )
    op.create_index(
        "ix_asana_integrations_webhook_url_token",
        "asana_integrations",
        ["webhook_url_token"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_asana_integrations_webhook_url_token", table_name="asana_integrations")
    op.drop_column("asana_integrations", "webhook_url_token")
